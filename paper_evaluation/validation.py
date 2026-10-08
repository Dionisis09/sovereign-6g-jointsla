"""Independent reconstruction from request exports and audit CSVs."""
import hashlib
import gzip
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import ndtr
from catalyst.reused import digest, write_json
from .accounting import POLICIES, LABELS, PRIMARY
from .experiments import ROOT, engine_hashes


def linear_quantile(values, probability):
    """Independent sorted-order interpolation, matching NumPy linear quantiles."""
    ordered = np.sort(np.asarray(values, dtype=float))
    position = (len(ordered)-1)*probability
    lower, upper = int(np.floor(position)), int(np.ceil(position))
    return float(ordered[lower]+(position-lower)*(ordered[upper]-ordered[lower]))


def reference_ci(values, key):
    salt = int.from_bytes(hashlib.sha256(str(key).encode("utf-8")).digest()[:4], "little")
    rng = np.random.default_rng(np.random.SeedSequence([73001, salt]))
    x = np.asarray(values, dtype=float)
    idx = rng.integers(0, len(x), (10_000, len(x)))
    means = x[idx].sum(axis=1)/len(x)
    return [linear_quantile(means, p) for p in (.025, .975)]


def reference_signed_rank(differences):
    """Reconstruct W/RBC and p using exact DP or the tie-adjusted normal CDF."""
    d = np.round(np.asarray(differences), 12)
    nonzero = d[d != 0]
    if not len(nonzero):
        return 0., 1., 0.
    ranks = pd.Series(np.abs(nonzero)).rank(method="average").to_numpy()
    plus, minus = ranks[nonzero>0].sum(), ranks[nonzero<0].sum()
    w = min(plus, minus)
    n = len(nonzero)
    if n == len(d) and len(np.unique(np.abs(nonzero))) == n:
        counts = np.zeros(n*(n+1)//2+1, dtype=np.int64)
        counts[0] = 1
        for rank in range(1, n+1):
            counts[rank:] += counts[:-rank].copy()
        p = min(1., 2*counts[:int(w)+1].sum()/2**n)
    else:
        ties = pd.Series(np.abs(nonzero)).value_counts().to_numpy()
        variance = (n*(n+1)*(2*n+1)-(ties**3-ties).sum()/2)/24
        z = (w-n*(n+1)/4)/np.sqrt(variance)
        p = 2*ndtr(-abs(z))
    return float(w), float(p), float((plus-minus)/(plus+minus))


def verify(output, check_report=True):
    raw = pd.read_csv(output/"raw_policy_results.csv")
    indexed = raw.set_index(["seed", "policy"])
    protocol = json.loads((output/"simulation_protocol.json").read_text(encoding="utf-8"))
    config = json.loads((output/"config.json").read_text(encoding="utf-8"))
    assert protocol["source_hashes"] == engine_hashes()
    assert protocol["config_hash"] == digest(config)
    seeds = protocol["seeds"]
    assert indexed.index.is_unique
    assert set(indexed.index) == {(s,p) for s in seeds for p in POLICIES}
    assert raw.groupby("policy").size().eq(30).all() and len(seeds) == 30
    assert np.isfinite(raw.select_dtypes(include="number").to_numpy()).all()
    inputs, references = {}, []
    for seed, group in raw.groupby("seed"):
        with gzip.open(output/"inputs"/f"seed_{seed:03d}.json.gz", "rt", encoding="utf-8") as stream:
            value = json.load(stream)
        inputs[seed] = value
        assert group.workload_hash.nunique() == group.traffic_hash.nunique() == 1
        assert digest(value) == group.workload_hash.iloc[0]
        tape = {key:value[key] for key in ("seed", "services", "requests", "traffic")}
        assert digest(tape) == group.traffic_hash.iloc[0]
        references.extend(dict(seed=seed, **r) for r in value["requests"])
    requests = pd.read_csv(output/"request_outcomes.csv.gz")
    reference = pd.DataFrame(references)
    joined = requests.merge(reference, on=["seed","request_id"], suffixes=("","_input"), validate="many_to_one")
    assert len(joined) == len(requests)
    for column in ("service_id", "arrival_slot", "arrival_s"):
        assert np.allclose(joined[column], joined[f"{column}_input"], atol=1e-12, rtol=0)
    for seed, f in joined.groupby("seed"):
        value = inputs[seed]
        services = {s["service_id"]:s for s in value["services"]}
        assert np.allclose(f.deadline_ms, f.service_id.map({sid:s["deadline_ms"] for sid,s in services.items()}))
        assert f.tier.eq(f.service_id.map({sid:s["tier"] for sid,s in services.items()})).all()
        valid = f.loc[f.latency_ms.notna()]
        delay = (valid.completion_s-valid.arrival_s)*1000
        components = valid[["service_queue_ms","node_queue_ms","network_ms","compute_ms","lifecycle_penalty_ms"]]
        assert np.allclose(delay,valid.latency_ms,atol=1e-6,rtol=0)
        assert np.allclose(delay,components.sum(axis=1),atol=1e-6,rtol=0)
        assert (components >= -1e-7).all().all()
        assert valid.breach.eq(valid.latency_ms > valid.deadline_ms).all()
        compute = valid.work_factor*(config["preprocess_ms"]+config["inference_ms"]+config["postprocess_ms"])
        assert np.allclose(compute,valid.compute_ms,atol=1e-6,rtol=0)
        ingress = valid.service_id.map({sid:s["ingress"] for sid,s in services.items()}).to_numpy(dtype=int)
        target = valid.node.to_numpy(dtype=int)
        bw = np.array([n["bandwidth_capacity_mbps"] for n in value["scenario"]["nodes"]])
        net = np.array(value["scenario"]["network_latency_ms"])[ingress,target]+1000*valid.payload_mbit/bw[target]
        assert np.allclose(net,valid.network_ms,atol=1e-6,rtol=0)
    latency_checks = 0
    for key, f in requests.groupby(["seed","policy"]):
        r = indexed.loc[key]
        assert f.request_id.nunique() == len(f) == len(inputs[key[0]]["requests"]) == r.total_requests
        assert set(f.request_id) == set(range(len(f)))
        completed = f.latency_ms.notna()
        dropped = f.get("dropped", pd.Series(False,index=f.index)).astype(bool)
        assert (completed | dropped | f.unplaced).all() and not (dropped & f.unplaced).any()
        assert f.loc[dropped | f.unplaced,"breach"].all()
        assert r.completed_requests == completed.sum() and r.dropped_requests == dropped.sum()
        assert r.sla_breaches == f.breach.sum() and np.isclose(r.sla_breach_rate,f.breach.sum()/len(f))
        assert np.isclose(r.drop_rate,dropped.sum()/len(f))
        latency = f.loc[completed,"latency_ms"].to_numpy()
        assert np.isclose(r.mean_request_latency_ms,latency.sum()/len(latency))
        assert np.isclose(r.mean_slot_latency_ms,f.groupby("arrival_slot").latency_ms.mean().mean())
        for metric, probability in (("median_latency_ms",.5),("p95_latency_ms",.95),("p99_latency_ms",.99)):
            assert np.isclose(r[metric],linear_quantile(latency,probability),atol=1e-7,rtol=0)
            latency_checks += 1
        assert r.completed_after_horizon == (f.completion_s > config["slots"]*config["slot_seconds"]).sum()
        for tier in ("Gold","Silver","Bronze"):
            sub = f.loc[f.tier == tier]
            assert r[f"{tier}_requests"] == len(sub) and r[f"{tier}_breaches"] == sub.breach.sum()
            assert np.isclose(r[f"{tier}_breach_rate"],sub.breach.sum()/len(sub))
    slots = pd.read_csv(output/"slot_trajectories.csv")
    nodes = pd.read_csv(output/"node_trajectories.csv")
    actions = pd.read_csv(output/"actions.csv")
    lifecycle = pd.read_csv(output/"lifecycle_events.csv")
    for key, r in indexed.iterrows():
        sf = slots.loc[(slots.seed==key[0]) & (slots.policy==key[1])]
        nf = nodes.loc[(nodes.seed==key[0]) & (nodes.policy==key[1])]
        af = actions.loc[(actions.seed==key[0]) & (actions.policy==key[1])]
        lf = lifecycle.loc[(lifecycle.seed==key[0]) & (lifecycle.policy==key[1])]
        assert len(sf)==config["slots"] and len(nf)==config["slots"]*config["node_count"]
        assert sf.requests.sum()==r.total_requests and sf.completed_requests.sum()==r.completed_requests
        for metric, kind in (("migrations","migrate"),("scale_outs","scale_up"),("scale_ins","scale_down")):
            assert r[metric] == af.kind.eq(kind).sum()
        assert r.cold_starts == lf.kind.eq("cold_start").sum()
        assert np.isclose(r.average_replicas,r.replica_seconds/(config["slots"]*config["slot_seconds"]))
        initial = sum(n is not None for n in inputs[key[0]]["initial"].values())
        assert r.peak_replicas==max(sf.replicas.max(),initial)
        for resource in ("cpu","gpu"):
            assert nf[f"{resource}_utilization"].between(-1e-8,1+1e-8).all()
            assert np.isclose(r[f"average_{resource}_utilization"],nf[f"{resource}_utilization"].mean())
    ledger = pd.read_csv(output/"reservation_events.csv")
    for key, f in ledger.groupby(["seed","policy"],sort=False):
        v=inputs[key[0]]
        caps=np.array([[n["cpu_capacity"],n["gpu_capacity"],n["bandwidth_capacity_mbps"]] for n in v["scenario"]["nodes"]])
        reserved=np.zeros_like(caps)
        for e in f.itertuples():
            s=v["services"][e.service_id]
            reserved[e.node]+=e.sign*np.array([s["cpu_cores"],s["gpu_vram_gb"],s["bandwidth_mbps"]])
            assert (reserved>=-1e-8).all() and (reserved<=caps+1e-8).all()
            assert np.allclose(reserved[e.node],[e.cpu_reserved,e.gpu_vram_reserved,e.bandwidth_reserved])
    summary = pd.read_csv(output/"summary_statistics.csv")
    assert np.isfinite(summary.select_dtypes(include="number").to_numpy()).all()
    for r in summary.itertuples():
        x=raw.loc[raw.policy==r.policy].sort_values("seed")[r.metric].to_numpy()
        assert r.n==len(x) and np.isclose(r.mean,x.mean()) and np.isclose(r.standard_deviation,x.std(ddof=1))
        assert np.isclose(r.median,np.median(x)) and np.isclose(r.min,x.min()) and np.isclose(r.max,x.max())
        ci=reference_ci(x,key=f"{(r.policy,)}:{r.metric}")
        assert np.allclose(ci,[r.ci95_lower,r.ci95_upper],atol=1e-8,rtol=0)
    tests = pd.read_csv(output/"paired_tests.csv")
    differences = pd.read_csv(output/"paired_seed_differences.csv")
    assert len(tests)==12 and len(differences)==360
    for r in tests.itertuples():
        pivot=raw.pivot(index="seed",columns="policy",values=r.metric).sort_index()
        a,b=pivot.sla_aware.to_numpy(),pivot[r.policy_B].to_numpy()
        d=b-a
        assert np.isclose(r.mean_A,a.mean()) and np.isclose(r.mean_B,b.mean())
        assert np.isclose(r.absolute_difference,d.mean()) and np.isclose(r.relative_improvement_percent,100*d.mean()/b.mean())
        stat,p,effect=reference_signed_rank(d)
        assert np.isclose(stat,r.test_statistic) and np.isclose(p,r.p_value,rtol=1e-8,atol=1e-14)
        assert np.isclose(effect,r.rank_biserial_correlation)
        assert [r.wins,r.ties,r.losses]==[int((np.round(d,12)>0).sum()),int((np.round(d,12)==0).sum()),int((np.round(d,12)<0).sum())]
        ci=reference_ci(d,key=f"paired:{r.policy_B}:{r.metric}")
        assert np.allclose(ci,[r.difference_ci95_lower,r.difference_ci95_upper])
        salt=int.from_bytes(hashlib.sha256(f"relative:{r.policy_B}:{r.metric}".encode()).digest()[:4],"little")
        rng=np.random.default_rng(np.random.SeedSequence([73001,salt]))
        indices=rng.integers(0,len(a),(10_000,len(a)))
        bm,am=b[indices].mean(axis=1),a[indices].mean(axis=1)
        ratios=100*(bm-am)/bm
        assert np.allclose([linear_quantile(ratios,.025),linear_quantile(ratios,.975)],
                           [r.relative_ci95_lower,r.relative_ci95_upper])
        df=differences.loc[(differences.baseline_policy==r.policy_B)&(differences.metric==r.metric)].sort_values("seed")
        assert df.seed.tolist()==list(pivot.index)
        assert np.allclose(df.absolute_difference,d) and np.allclose(df.relative_difference_percent,100*d/b)
        assert np.allclose(df.baseline_value,b) and np.allclose(df.sla_aware_value,a)
    last=0.
    for rank, idx in enumerate(tests.p_value.sort_values(kind="stable").index):
        last=min(1.,max(last,tests.loc[idx,"p_value"]*(len(tests)-rank)))
        assert np.isclose(last,tests.loc[idx,"p_value_holm"],atol=1e-14)
    assert tests.significant_at_0_05.eq(tests.p_value<.05).all()
    assert tests.significant_holm_0_05.eq(tests.p_value_holm<.05).all()
    assert tests.supported_improvement.eq((tests.p_value_holm<.05)&(tests.absolute_difference>0)&(tests.difference_ci95_lower>0)).all()
    if (output/"capacity_summary.csv").exists():
        capacity=pd.read_csv(output/"capacity_summary.csv")
        source=pd.read_csv(ROOT/"results/capacity_sweep/combined_runs.csv")
        assert capacity.nodes.tolist()==list(range(5,11))
        for r in capacity.itertuples():
            group=source.loc[source.node_count==r.nodes].sort_values("seed")
            assert group.seed.tolist()==list(range(30)) and r.n==30
            for metric,field,column,factor in (("sla_breach_rate","breach_rate","sla_breach_pct",.01),
                                              ("mean_request_latency_ms","latency_ms","average_latency_ms",1),
                                              ("mean_slot_latency_ms","slot_latency_ms","time_average_slot_latency_ms",1)):
                x=group[column].to_numpy()*factor
                assert np.isclose(getattr(r,f"mean_{field}"),x.mean())
                assert np.allclose(reference_ci(x,f"capacity:{r.nodes}:{metric}"),
                                   [getattr(r,f"{field}_ci95_lower"),getattr(r,f"{field}_ci95_upper")])
    if (output/"scenario_summary_statistics.csv").exists():
        scenario_raw=pd.read_csv(output/"scenario_raw_results.csv")
        for r in pd.read_csv(output/"scenario_summary_statistics.csv").itertuples():
            x=scenario_raw.loc[scenario_raw.scenario==r.scenario].sort_values("seed")[r.metric].to_numpy()
            assert r.n==30 and np.isclose(r.mean,x.mean())
            assert np.allclose(reference_ci(x,f"{(r.scenario,)}:{r.metric}"),[r.ci95_lower,r.ci95_upper])
    if check_report:
        report=(output/"report.md").read_text(encoding="utf-8")
        for title in ("Experimental Setup","Main Results","SLA Compliance","Latency","Tail Latency","Per-Tier Analysis","Statistical Significance","Effect Sizes","Reconfiguration Costs","Capacity Analysis","Admission Control","Prewarming","Main Findings","Limitations"):
            assert f"# {title}" in report
        for policy in POLICIES:
            cells=[]
            for metric in PRIMARY:
                r=summary.loc[(summary.policy==policy)&(summary.metric==metric)].iloc[0]
                factor=100 if metric=="sla_breach_rate" else 1
                cells.append(f"{r['mean']*factor:.2f} [{r.ci95_lower*factor:.2f}, {r.ci95_upper*factor:.2f}]")
            assert "| "+" | ".join([LABELS[policy],*cells])+" |" in report
        claims=pd.read_csv(output/"claim_ledger.csv")
        for r in claims.itertuples():
            pair=tests.loc[(tests.policy_B==r.baseline)&(tests.metric==r.metric)].iloc[0]
            assert pair.supported_improvement and pair.p_value_holm<.05 and pair.difference_ci95_lower>0
            pivot=raw.pivot(index="seed",columns="policy",values=r.metric)
            improvement=100*(pivot[r.baseline].mean()-pivot.sla_aware.mean())/pivot[r.baseline].mean()
            assert np.isclose(improvement,r.relative_improvement_percent)
            assert f"{improvement:.2f}%" in r.sentence and r.sentence in report
        from PIL import Image
        for path in (output/"figures").glob("*.png"):
            with Image.open(path) as picture:
                assert min(picture.info["dpi"])>=299
            assert path.with_suffix(".svg").exists() and path.with_suffix(".pdf").exists()
    analysis=json.loads((output/"analysis_protocol.json").read_text(encoding="utf-8"))
    for path,h in analysis["source_hashes"].items():
        assert digest((ROOT/path).read_text(encoding="utf-8"))==h
    report=dict(successful_runs=len(raw),seed_range=[min(seeds),max(seeds)],runs_per_policy=raw.groupby("policy").size().to_dict(),
                request_outcomes_checked=len(requests),request_quantiles_checked=latency_checks,
                pairing_and_input_hashes_verified=True,completion_and_tier_accounting_verified=True,
                latency_components_and_capacity_verified=True,all_summary_ci_and_statistics_verified=True,
                signed_rank_p_values_independently_reconstructed=True,holm_and_effect_sizes_verified=True,
                supplementary_confidence_intervals_verified=True,
                all_seed_differences_retained=True,report_claims_verified=check_report,
                engine_source_unchanged=True,figures_300dpi_and_vectors_verified=check_report)
    write_json(output/"validation.json",report)
    return report
