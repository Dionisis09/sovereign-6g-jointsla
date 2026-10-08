"""Seed-level bootstrap CIs and paired signed-rank comparisons.

All primary metrics are lower-is-better. A positive difference/effect means
SLA-aware improves over the baseline. No request-level pseudoreplication.
"""
import hashlib
import numpy as np
import pandas as pd
from scipy.stats import rankdata, wilcoxon
from .accounting import POLICIES, PRIMARY, validate_pairing

BOOTSTRAP_SEED = 73001
RESAMPLES = 10_000


def rng_for(key, seed=BOOTSTRAP_SEED):
    salt = int.from_bytes(hashlib.sha256(str(key).encode("utf-8")).digest()[:4], "little")
    return np.random.default_rng(np.random.SeedSequence([seed, salt]))


def bootstrap_mean_ci(values, key="default", resamples=RESAMPLES, seed=BOOTSTRAP_SEED):
    """95% percentile bootstrap CI of the seed-level arithmetic mean.

    Resample complete seeds, not requests. Constant samples give point CIs.
    This finite-n Monte Carlo interval has no distribution-free coverage claim.
    """
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or len(x) < 2 or not np.isfinite(x).all():
        raise ValueError("CI requires >=2 finite seed observations")
    if resamples < 10_000:
        raise ValueError("at least 10,000 bootstrap resamples required")
    indices = rng_for(key, seed).integers(0, len(x), size=(resamples, len(x)))
    means = x[indices].mean(axis=1)
    return tuple(float(v) for v in np.quantile(means, [.025, .975], method="linear"))


def summarize(raw, group_columns=("policy",), exclude=()):
    """Long-format mean, SD, median, range and mean CI for every numeric metric."""
    metrics = [c for c in raw.select_dtypes(include="number") if c not in {"seed", *group_columns, *exclude}]
    rows = []
    for key, group in raw.groupby(list(group_columns), sort=False):
        key = key if isinstance(key, tuple) else (key,)
        metadata = dict(zip(group_columns, key))
        for metric in metrics:
            x = group.sort_values("seed")[metric].to_numpy(dtype=float)
            # Missing supplemental per-node metrics are not silently imputed.
            finite = x[np.isfinite(x)]
            if not len(finite):
                continue
            if len(finite) != len(x):
                raise ValueError(f"partial missing metric {metadata}: {metric}")
            lo, hi = bootstrap_mean_ci(x, key=f"{key}:{metric}")
            rows.append(dict(**metadata, metric=metric, n=len(x), mean=float(x.mean()),
                             standard_deviation=float(x.std(ddof=1)), median=float(np.median(x)),
                             min=float(x.min()), max=float(x.max()), ci95_lower=lo, ci95_upper=hi,
                             ci_method="percentile bootstrap of mean across seeds", resamples=RESAMPLES))
    return pd.DataFrame(rows)


def signed_rank(improvements):
    """Two-sided Wilcoxon; exclude zeros, average tied ranks, positive RBC=benefit.

    Round differences at 12 decimal places before ranking to avoid spurious
    numerical ties. Use exact only with no zeros/tied magnitudes, otherwise
    SciPy's tie-corrected asymptotic method. All-zero data: W=0, p=1, RBC=0.
    """
    d = np.round(np.asarray(improvements, dtype=float), 12)
    if d.ndim != 1 or not np.isfinite(d).all():
        raise ValueError("invalid paired differences")
    nz = d[d != 0]
    if not len(nz):
        return dict(test_statistic=0., p_value=1., rank_biserial_correlation=0.,
                    effective_nonzero_n=0, wilcoxon_method="all-zero convention")
    ranks = rankdata(np.abs(nz), method="average")
    positive, negative = ranks[nz > 0].sum(), ranks[nz < 0].sum()
    method = "exact" if len(nz) == len(d) and len(np.unique(np.abs(nz))) == len(nz) else "asymptotic"
    result = wilcoxon(d, zero_method="wilcox", correction=False, alternative="two-sided", method=method)
    return dict(test_statistic=float(result.statistic), p_value=float(result.pvalue),
                rank_biserial_correlation=float((positive-negative)/(positive+negative)),
                effective_nonzero_n=len(nz), wilcoxon_method=method)


def holm_adjust(p_values):
    """Holm step-down familywise correction, preserving input order."""
    p = np.asarray(p_values, dtype=float)
    order = np.argsort(p, kind="stable")
    adjusted = np.empty(len(p))
    adjusted[order] = np.minimum(1., np.maximum.accumulate(p[order]*(len(p)-np.arange(len(p)))))
    return adjusted


def paired_analysis(raw, seeds):
    validate_pairing(raw, seeds)
    rows, differences = [], []
    for baseline in POLICIES[:-1]:
        for metric in PRIMARY:
            pivot = raw.pivot(index="seed", columns="policy", values=metric).sort_index()
            a, b = pivot.sla_aware.to_numpy(), pivot[baseline].to_numpy()
            d = b-a
            test = signed_rank(d)
            ci = bootstrap_mean_ci(d, key=f"paired:{baseline}:{metric}")
            indices = rng_for(f"relative:{baseline}:{metric}").integers(0, len(a), (RESAMPLES, len(a)))
            base_means, proposed_means = b[indices].mean(axis=1), a[indices].mean(axis=1)
            if np.any(base_means == 0) or b.mean() == 0 or np.any(b == 0):
                raise ValueError("relative improvement undefined for zero baseline")
            relative_ci = np.quantile(100*(base_means-proposed_means)/base_means, [.025, .975])
            signs = np.round(d, 12)
            rows.append(dict(metric=metric, policy_A="sla_aware", policy_B=baseline, n=len(a),
                             mean_A=float(a.mean()), mean_B=float(b.mean()),
                             absolute_difference=float(d.mean()),
                             difference_ci95_lower=ci[0], difference_ci95_upper=ci[1],
                             relative_improvement_percent=float(100*d.mean()/b.mean()),
                             relative_ci95_lower=float(relative_ci[0]), relative_ci95_upper=float(relative_ci[1]),
                             test_used="Wilcoxon signed-rank, two-sided", **test,
                             significant_at_0_05=test["p_value"] < .05,
                             wins=int((signs > 0).sum()), ties=int((signs == 0).sum()), losses=int((signs < 0).sum()),
                             difference_direction="baseline minus SLA-aware; positive is improvement"))
            for seed, bv, av, delta in zip(pivot.index, b, a, d):
                differences.append(dict(seed=int(seed), baseline_policy=baseline, metric=metric,
                                        baseline_value=float(bv), sla_aware_value=float(av),
                                        absolute_difference=float(delta), relative_difference_percent=float(100*delta/bv),
                                        outcome="win" if round(delta, 12)>0 else "loss" if round(delta, 12)<0 else "tie"))
    tests = pd.DataFrame(rows)
    tests["p_value_holm"] = holm_adjust(tests.p_value)
    tests["significant_holm_0_05"] = tests.p_value_holm < .05
    tests["supported_improvement"] = tests.significant_holm_0_05 & (tests.absolute_difference > 0) & (tests.difference_ci95_lower > 0)
    return tests, pd.DataFrame(differences)
