"""Fixed paired matrix and two ablations; no automatic parameter search."""
import argparse
from dataclasses import asdict
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import numpy as np
import pandas as pd
from .engine import Engine
from .policies import PRIMARY, ABLATIONS, Action
from .reused import write_json, write_gzip, digest
from .scenario import load_config, matrix, workload


def freeze(output, config_path):
    files = sorted(Path("catalyst").glob("*.py")) + [Path(config_path), Path("docs/protocol.md")]
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    path = output / "pre_run_manifest.json"
    if path.exists():
        recorded = json.loads(path.read_text(encoding="utf-8"))
        if hashes != recorded["files"]:
            raise RuntimeError("source/config/protocol changed: use a fresh output directory; do not mix runs")
        return
    write_json(path, dict(files=hashes, python=platform.python_version(),
                         dependencies={name: importlib.metadata.version(name) for name in
                                       ("simpy", "pydantic", "numpy", "pandas", "matplotlib", "pytest")},
                         branch=subprocess.check_output(["git", "branch", "--show-current"], text=True).strip(),
                         protocol="docs/protocol.md", stress_tuned_after_results=False,
                         s0_fixture_correction="Initial 40-rps S0 queued during rollout; preserved in results/phase0. S0 now 10 rps; stress parameters unchanged."))


def audit_blocks(engine):
    """Bounded counterfactual outcome audit, completely outside controller code."""
    config, audited = engine.config, []
    for decision in engine.decisions:
        for blocked in decision["rejected"]:
            if blocked["source"] != "contract":
                continue
            time_s = decision["time_s"]
            horizon = time_s + config.metric_window_s
            record = dict(time_s=time_s, action=blocked["action"], reasons=blocked["reasons"],
                          horizon_s=config.metric_window_s, false_block=None)
            if horizon <= config.duration_s:
                shadow = Engine(config, engine.scenario, engine.tape, engine.policy,
                                forced=(time_s, Action(blocked["action"]))).run(stop_at=horizon)
                samples = [s for s in shadow.samples if time_s < s["time_s"] <= horizon]
                record["shadow_breach_seconds"] = sum(bool(s["violations"]) for s in samples) * config.tick_s
                record["false_block"] = not any(s["violations"] for s in samples)
            audited.append(record)
    return audited


def run_stage(config, stage, output):
    policies = ABLATIONS if stage == "ablations" else PRIMARY
    scenarios = [s for s in matrix(config) if stage == "ablations" or
                 (s.family == "S0") == (stage == "negative")]
    summaries = []
    for scenario in scenarios:
        for seed in config.seeds:
            tape = workload(config, scenario, seed)
            case = output / "evidence" / f"{scenario.family}-L{scenario.level}-seed{seed}"
            case.mkdir(parents=True, exist_ok=True)
            write_gzip(case / "workload.json.gz", dict(sha256=tape.sha256, requests=[asdict(r) for r in tape.requests],
                                                       scenario=scenario.model_dump(), seed=seed))
            for policy in policies:
                engine = Engine(config, scenario, tape, policy).run()
                blocks = audit_blocks(engine)
                summary = engine.summary()
                summary.update(seed=seed, false_blocks=sum(b["false_block"] is True for b in blocks),
                               audited_contract_blocks=sum(b["false_block"] is not None for b in blocks),
                               censored_contract_blocks=sum(b["false_block"] is None for b in blocks))
                summaries.append(summary)
                evidence = dict(summary=summary, decisions=engine.decisions, samples=engine.samples,
                                false_block_audit=blocks, outcomes=sorted(engine.outcomes, key=lambda r: r["request_id"]))
                write_gzip(case / f"{policy}.json.gz", evidence)
            print(f"{stage}: {scenario.family} L{scenario.level} seed {seed} ({len(tape.requests)} requests)", flush=True)
    write_json(output / f"{stage}.json", summaries)
    if stage == "negative":
        grouped = pd.DataFrame(summaries).groupby("seed")
        fields = ["outcomes_hash", "total_service_contract_breach_seconds", "rollout_completion_time_s"]
        equality = all(group[fields].nunique(dropna=False).max() == 1 for _, group in grouped)
        control = check_negative(summaries, config)
        control.update(exact_equality=bool(equality), runs=len(summaries))
        write_json(output / "negative_control.json", control)
        print(f"S0 checks: {control}", flush=True)
        if not control["passed"]:
            raise RuntimeError("S0 safety/comparability checks failed; inspect evidence")


def check_negative(rows, config):
    frame = pd.DataFrame(rows)
    decisive = frame[frame.policy.isin(("B1", "CATALYST"))]
    exact = all(group[["outcomes_hash", "rollout_completion_time_s"]].nunique(dropna=False).max() == 1
                for _, group in decisive.groupby("seed"))
    breach_equal = bool((frame.groupby("seed").total_service_contract_breach_seconds.nunique() == 1).all())
    averages = frame.groupby("policy")[["p99_latency_ms", "rollout_completion_time_s"]].mean()
    completion_spread = float(averages.rollout_completion_time_s.max() - averages.rollout_completion_time_s.min())
    latency_spread = float(averages.p99_latency_ms.max() - averages.p99_latency_ms.min())
    passed = exact and breach_equal and frame.rollout_completed.all() and completion_spread <= config.rollout_stage_hold_s and latency_spread <= 5
    return dict(passed=bool(passed), b1_catalyst_exact=bool(exact), primary_metric_exact=breach_equal,
                mean_completion_spread_s=completion_spread, mean_p99_spread_ms=latency_spread)


def comparisons(frame, config):
    rng = np.random.default_rng(20261006)
    rows = []
    for (family, level), group in frame.groupby(["family", "level"]):
        pairs = group.pivot(index="seed", columns="policy", values="total_service_contract_breach_seconds")
        if set(pairs.columns) != set(PRIMARY + ABLATIONS) or pairs.isna().any().any():
            raise ValueError("complete primary/ablation pairs are required")
        baseline, catalyst = pairs.B1.to_numpy(), pairs.CATALYST.to_numpy()
        difference = baseline - catalyst
        interval = np.quantile(difference[rng.integers(0, len(difference), (10000, len(difference)))].mean(axis=1), [.025, .975])
        total = float(baseline.sum())
        improvement = 100 * float(difference.sum()) / total if total > 0 else None
        cat = group[group.policy == "CATALYST"].set_index("seed").sort_index()
        b1 = group[group.policy == "B1"].set_index("seed").sort_index()
        false_rate = float(cat.false_blocks.sum() / cat.audited_contract_blocks.sum()) if cat.audited_contract_blocks.sum() else 0.
        delay = float((cat.rollout_completion_time_s - b1.rollout_completion_time_s).mean()) if cat.rollout_completed.all() and b1.rollout_completed.all() else None
        a1_equal = bool((pairs.A1 == pairs.B1).all())
        a2_loss = 100 * float((pairs.A2 - pairs.CATALYST).sum()) / total if total > 0 else None
        qualifies = bool(family != "S0" and improvement is not None and improvement >= 5 and interval[0] > 0
                         and (difference > 0).sum() >= 8 and cat.rollout_completed.all() and b1.rollout_completed.all()
                         and false_rate <= .1 and cat.censored_contract_blocks.sum() == 0
                         and delay is not None and delay <= config.rollout_stage_hold_s
                         and a1_equal and a2_loss is not None and a2_loss >= 5)
        rows.append(dict(family=family, level=int(level), paired_seeds=len(pairs),
                         b1_breach_mean_s=float(baseline.mean()), catalyst_breach_mean_s=float(catalyst.mean()),
                         improvement_pct=improvement, paired_difference_mean_s=float(difference.mean()),
                         paired_difference_ci95_s=interval.tolist(), improved_seeds=int((difference > 0).sum()),
                         rollout_completed_seeds=int(cat.rollout_completed.sum()), false_block_rate=false_rate,
                         completion_delay_mean_s=delay, a1_equals_b1=a1_equal, a2_loss_pct=a2_loss,
                         qualifying=qualifies))
    return rows


def analyze(config, output):
    rows = [row for stage in ("negative", "stress", "ablations") for row in
            json.loads((output / f"{stage}.json").read_text(encoding="utf-8"))]
    frame = pd.DataFrame(rows)
    expected = len(list(matrix(config))) * len(config.seeds) * 5
    if len(frame) != expected or frame.duplicated(["family", "level", "seed", "policy"]).any():
        raise ValueError("unexpected run matrix")
    if (frame.groupby(["family", "level", "seed"]).tape_hash.nunique() != 1).any():
        raise ValueError("unpaired input tapes")
    if (frame.groupby(["family", "level", "seed"]).request_count.nunique() != 1).any() or frame.rejected_requests.sum():
        raise ValueError("request accounting failed")
    # A1 is an exact mechanism-equivalence check, including individual outcomes.
    paired_outcomes = frame.pivot(index=["family", "level", "seed"], columns="policy", values="outcomes_hash")
    if not (paired_outcomes.A1 == paired_outcomes.B1).all():
        raise ValueError("A1 must reproduce B1 request outcomes")
    cells = comparisons(frame, config)
    families = [family for family in ("S1", "S2", "S3") if
                sum(row["qualifying"] for row in cells if row["family"] == family) >= 2]
    negative = json.loads((output / "negative_control.json").read_text())
    negative_ok = negative["passed"]
    decision = "FAIL"
    if len(families) >= 2 and negative_ok and frame.rollout_completed.all():
        strong = all(sum(row["qualifying"] and row["improvement_pct"] >= 10 for row in cells
                         if row["family"] == family) >= 2 for family in families)
        decision = "STRONG SIGNAL" if strong else "LOW-C CONTINUE"
    result = dict(decision=decision, runs=len(frame), primary_runs=int(frame.policy.isin(PRIMARY).sum()),
                  ablation_runs=int(frame.policy.isin(ABLATIONS).sum()), qualifying_families=families,
                  negative_control=negative, rejected_requests=int(frame.rejected_requests.sum()),
                  cells=cells, no_expansion=True)
    write_json(output / "analysis.json", result)
    frame.to_csv(output / "runs.csv", index=False)
    table = frame.groupby(["family", "level", "policy"])[[
        "total_service_contract_breach_seconds", "p99_latency_ms", "sla_violation_rate",
        "rollout_completion_time_s", "interruption_time_s", "blocked_actions", "false_blocks",
        "rollback_count", "worker_seconds"]].mean().reset_index()
    table.to_csv(output / "summary.csv", index=False)
    plot(table, output)
    report(result, table, frame, output)
    print(json.dumps({k: result[k] for k in ("decision", "runs", "qualifying_families", "negative_control")}), flush=True)


def plot(table, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(1, 4, figsize=(13, 3.7), sharey=True)
    for axis, family in zip(axes, ("S0", "S1", "S2", "S3")):
        for policy in PRIMARY + ABLATIONS:
            data = table[(table.family == family) & (table.policy == policy)]
            axis.plot(data.level, data.total_service_contract_breach_seconds, marker="o", label=policy,
                      linestyle="--" if policy in ABLATIONS else "-")
        axis.set_title(family)
        axis.set_xlabel("Fixed stress level")
        axis.set_xticks([0] if family == "S0" else [1, 2, 3])
        axis.grid(alpha=.2)
    axes[0].set_ylabel("Mean contract breach seconds")
    axes[-1].legend(fontsize=8)
    figure.suptitle("CATALYST Phase 0 — ten paired seeds per point; synthetic model")
    figure.tight_layout()
    figure.savefig(output / "breach_seconds.png", dpi=180)
    figure.savefig(output / "breach_seconds.svg")
    plt.close(figure)


def report(result, table, frame, output):
    lines = [f"# CATALYST Phase 0: {result['decision']}", "",
             f"{result['primary_runs']} primary runs + {result['ablation_runs']} ablation runs. "
             "100 matched tapes; ten seeds per scenario/level. Parameters were fixed before running.", "",
             f"S0 passed: {result['negative_control']['passed']}; B1/CATALYST exact equality: "
             f"{result['negative_control']['b1_catalyst_exact']}; all-policy primary-metric equality: "
             f"{result['negative_control']['primary_metric_exact']}. Rejected requests: {result['rejected_requests']}.", "",
             "Validation correction: the original 40-rps S0 fixture produced resource pressure. "
             "It was reduced to 10 rps before stress experiments; both pilot controls are preserved. "
             "A draft requirement for every B0 request to match B1 exactly was also corrected to the user's "
             "near-equality requirement: B1/CATALYST remain exact; all-policy breach seconds match; "
             "aggregate completion spread <=3 s and p99 spread <=5 ms. These corrections were made after "
             "seeing S0, and are disclosed rather than described as originally preregistered. "
             "The S1-S3 parameters and hypothesis rules were unchanged.", "",
             "This is a synthetic feasibility result, not a validated 6G deployment or a novelty claim.", "",
             "| Scenario | B1 breach s | CATALYST breach s | Reduction | Improved seeds | Paired delta 95% CI, s | Qualifies |",
             "|---|---:|---:|---:|---:|---|---|"]
    for row in result["cells"]:
        gain = f"{row['improvement_pct']:.1f}%" if row["improvement_pct"] is not None else "n/a (zero B1 breach)"
        lo, hi = row["paired_difference_ci95_s"]
        lines.append(f"| {row['family']}/L{row['level']} | {row['b1_breach_mean_s']:.2f} | {row['catalyst_breach_mean_s']:.2f} | {gain} | {row['improved_seeds']}/10 | [{lo:.2f}, {hi:.2f}] | {row['qualifying']} |")
    lines += ["", "The CI resamples paired seeds, not individual requests. Improvement is relative to B1; "
              "a positive paired delta favors CATALYST. B0 is explanatory only.", "",
              "| Scenario | CATALYST completion seeds | Mean completion delay vs B1, s | False contract block rate | A1=B1 | A2 loss vs CATALYST, % of B1 breach |",
              "|---|---:|---:|---:|---|---:|"]
    for row in result["cells"]:
        delay = f"{row['completion_delay_mean_s']:.2f}" if row["completion_delay_mean_s"] is not None else "incomplete"
        loss = f"{row['a2_loss_pct']:.1f}" if row["a2_loss_pct"] is not None else "n/a"
        lines.append(f"| {row['family']}/L{row['level']} | {row['rollout_completed_seeds']}/10 | {delay} | {100*row['false_block_rate']:.1f}% | {row['a1_equals_b1']} | {loss} |")
    lines += ["", "False-block rates use independent, two-second forced-action shadow replays. "
              "They are bounded diagnostics. Full secondary metrics and resource seconds are in `summary.csv`; "
              "all seed-level metrics are in `runs.csv`. Compressed evidence retains each request, sample, "
              "decision, rejection reason and counterfactual audit. All admitted requests drain.", "",
              f"Rollouts completed in {int(frame.rollout_completed.sum())}/{len(frame)} runs. "
              f"CATALYST false blocks: {int(frame[frame.policy=='CATALYST'].false_blocks.sum())}/"
              f"{int(frame[frame.policy=='CATALYST'].audited_contract_blocks.sum())} audited contract vetoes.", "",
              "Interpretation: a level needs >=5% reduction with positive paired CI, at least eight improved seeds, "
              "completed rollout, <=10% false blocks, <=3 s extra completion time, and both ablation checks. "
              "Two levels in each of two stressed families are required. See the preregistered `docs/protocol.md`.", "",
              "## Reuse and code quality", "",
              "EXISTING CODE REUSED: AIMCO `jsonable`/`digest`; VISTA `quantile`, `write_json`, `write_gzip`. "
              "See `docs/reuse-provenance.json` for exact source hashes. Immutable tapes, public-only snapshots "
              "and paired request accounting adapt established prior patterns.", "",
              "EXTERNAL/STANDARD LIBRARIES REUSED: SimPy, Pydantic, NumPy, pandas, matplotlib, pytest; "
              "dataclasses, enum, collections, hashlib, JSON, gzip, argparse, pathlib, importlib.metadata.", "",
              "NEW RESEARCH-SPECIFIC CODE: four-clause compiler, shared local safety and cross-layer action gate; "
              "minimal service binding and paired decision analysis. Generic scheduling, validation, quantiles, "
              "storage, plotting and random sampling use reused code or established libraries.", "",
              "UNNECESSARY COMPONENTS NOT IMPLEMENTED: multi-tenancy, agents, Kubernetes, OpenNebula, RL, "
              "digital twins, extra baselines/ablations, deployment integration, broad policy language, six simulators.", "",
              "## Limits", "",
              "Model quality and service/network profiles are stipulated. The gate sums layer p99 predictions, "
              "a conservative heuristic rather than an exact end-to-end quantile. The local predictor is shared "
              "by B1 and CATALYST and can be inaccurate during transitions. One-second sampled breach durations "
              "and two-second windows may miss shorter violations. Availability counts late requests, while requests "
              "are never dropped. Default zero update outage makes disruption/availability mainly diagnostic clauses. "
              "No capacity event is added to the primary matrix. Stronger calibrated predictors or tighter local "
              "latency budgets could erase a composition benefit. Resource use may differ despite identical limits.", "",
              "Phase 0 stops here. No matrix expansion, result-driven tuning, or rescued novelty claim."]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/phase0.json")
    parser.add_argument("--output", default="results/phase0-v1")
    parser.add_argument("--stage", choices=("negative", "stress", "ablations", "analyze", "all"), default="all")
    args = parser.parse_args()
    config, output = load_config(args.config), Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    freeze(output, args.config)
    if args.stage == "all":
        for stage in ("negative", "stress", "ablations"):
            run_stage(config, stage, output)
        analyze(config, output)
    elif args.stage == "analyze":
        analyze(config, output)
    else:
        if args.stage == "stress" and (not (output / "negative_control.json").exists() or
            not json.loads((output / "negative_control.json").read_text())["passed"]):
            raise RuntimeError("run and pass S0 first")
        run_stage(config, args.stage, output)


if __name__ == "__main__":
    main()
