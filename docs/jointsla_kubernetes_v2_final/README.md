# JointSLA final research package

Finalized on 9 October 2026 from completed Kubernetes comparison v2. Original experiments, sources, results and earlier reports remain unchanged. No new experimental treatment or traffic is part of this publication integration.

JointSLA significantly reduces all-offered SLA failures against the registered core baselines in this short CPU burst regime. It uses **more target replica-seconds**. General resource efficiency, independent routing superiority and attainment of the below-15% target are unsupported.

| Policy | SLA failures mean ± sample SD | Completed p95 mean ± sample SD | HTTP 503 mean ± sample SD | Target replica-seconds mean ± sample SD |
| --- | ---: | ---: | ---: | ---: |
| Static two replicas | 61.50 ± 7.85% | 320.99 ± 67.12 ms | 43.22 ± 8.03% | 61.90 ± 0.10 |
| Reactive | 61.43 ± 6.94% | 322.85 ± 55.60 ms | 43.16 ± 7.48% | 65.12 ± 3.39 |
| Native HPA | 62.39 ± 7.37% | 328.26 ± 58.23 ms | 43.76 ± 7.92% | 64.03 ± 4.65 |
| JointSLA | 49.89 ± 8.12% | 318.63 ± 47.74 ms | 33.98 ± 7.75% | 103.45 ± 14.60 |

Primary JointSLA-minus-reactive effect: **−11.5390625 percentage points**, 95% paired bootstrap interval **[−13.984375, −9.057291666666668]**, Holm-corrected p **3.725290298461914e−08**. Target replica-time increases **58.8448662806198%**, as a ratio of policy means. Replica-time is a deployment-time proxy, not actual CPU use, energy or billing.

## Read the final artifacts

- [Full technical report in Word](JointSLA_Final_Technical_Report.docx), with [Markdown source](JointSLA_Final_Technical_Report.md).
- [Conference paper draft in Word](JointSLA_Conference_Paper_Draft.docx), with [Markdown source](JointSLA_Conference_Paper_Draft.md).
- [Editable fourteen-slide presentation](JointSLA_Conference_Presentation.pptx). Six native charts include embedded data workbooks.
- [Final consistency and preservation check](FINAL_CONSISTENCY_CHECK.md).
- [Shared numeric claim source](canonical_results.json) and [document content model](publication_content.json).

The paper is a venue-neutral draft. Authors, affiliations, submission venue and its final template remain to be supplied before submission.

## Tables and figures

Tables retain full numeric precision. Means and standard deviations are calculated from thirty run-level values. Completed p95 is conditional on completion. All rejections remain in the all-offered failure denominator.

- [All 180 runs](tables/all_180_runs.csv)
- [Policy summary with sample standard deviations](tables/policy_summary.csv)
- [Exact frozen paired intervals and corrected p-values](tables/paired_sla_comparisons.csv)
- [Tier counts and rates](tables/per_tier_failures.csv)
- [Failure categories](tables/failure_attribution.csv)
- [Performance and resource trade-off](tables/resource_tradeoff.csv)
- [Ablation results](tables/ablation_results.csv)

Seven figures are available in **PNG and vector PDF** in `figures/`: SLA failures, completed p95, HTTP 503, target replica-time, tier failures, paired effects/ablations and performance versus resource cost. Bar-plot error bars show **sample SD**, while the paired-effect plot shows **95% paired block-bootstrap intervals**. Slides display policy means; their notes preserve the interpretation and provenance.

## Evidence preservation

[Kubernetes_v2_complete_evidence.zip](evidence/Kubernetes_v2_complete_evidence.zip) contains 1,480 original raw, curated, protocol and frozen-source files with their original project-relative paths. [V2_SOURCE_SEAL.json](evidence/V2_SOURCE_SEAL.json) records every SHA-256 and the archive checksum. [HISTORICAL_RESULTS_SEAL.json](evidence/HISTORICAL_RESULTS_SEAL.json) records hashes, sizes and timestamps for 24,364 older files under `results/`. Those older datasets remain in the project and are not duplicated into this compact publication archive. The original v2 tree includes all 180 request CSVs, pod timelines, action/event logs, reset/preflight state, manifests and per-trial checks.

This is local archival preservation. It is not an independent-device backup or a public artifact deposit. Container/model binaries remain locally available outside the package and are identified by frozen image/model metadata. Credentials, kubeconfigs and Grafana passwords are excluded.

## Offline verification and regeneration

Run these commands from the project root. Verification is read-only and does not need Kubernetes or external Python dependencies.

```powershell
.venv/Scripts/python.exe docs/jointsla_kubernetes_v2_final/verify_preservation.py --originals
.venv/Scripts/python.exe docs/jointsla_kubernetes_v2_final/validate_publication.py
```

To verify the evidence archive from a copied package, omit `--originals`. The originals option requires the original project-relative paths. Package hashes in `PACKAGE_MANIFEST.json` allow independent verification of the final documents, tables, figures and source scripts.

To regenerate publication tables/figures in a **separate scratch directory**, leaving the finalized package untouched:

```powershell
.venv/Scripts/python.exe docs/jointsla_kubernetes_v2_final/reproduce_publication_analysis.py --output .cache/publication_v2_reproduction
```

Scientific dependency versions are retained in [requirements-analysis.txt](requirements-analysis.txt), copied from the frozen benchmark environment. Analysis runs offline against existing curated CSVs. Its descriptive resource bootstrap seed is 271830 with 10,000 resamples. Frozen SLA intervals and p-values are copied exactly, not silently recalculated with a different random stream. The original independent request reconstruction code is preserved in the evidence archive.

## Original experimental protocol and deployment

Thirty serial paired blocks use seeds 1001–1030, six arms, 1,280 requests at 120 requests/s, concurrency 32 and Gold/Silver/Bronze deadlines of 200/400/800 ms. Five randomized Latin cycles balance positions with seed 39107. Models are preconditioned identically, settle is 35 s, and follow-up is 20 s. Core SLA bootstrap seed is 39108. Native HPA retains real timing defaults. A disclosed 91.65-minute user pause affects one exploratory arm before its burst; no requests were offered during the pause.

The historical one-command local deployment is:

```powershell
.cache/infra-venv/Scripts/python.exe -m prototype.kubernetes.deploy --lab validation --skip-build
```

It requires Docker Desktop, existing pinned images, kind/kubectl and the project environment. See the archived registered protocol and `INFRASTRUCTURE_VALIDATION.md` for bootstrap and setup. Deployment does not itself regenerate results. The original benchmark pipeline is `python -m prototype.benchmark.pipeline`; it is documented for provenance and **was not rerun** during finalization. A new scientific run must use a new output identity and leave v2 frozen evidence intact.

## Interpretation boundary

The real cluster executes pretrained MobileNetV3-Large on CPU, with synthetic tensors on one virtual node and one physical host. Simulator results, hardware profile inputs and the historical 1,420-request infrastructure audit are separate evidence. Neither 38.83% nor 47.27% is a matched baseline for 49.89%. The router ablation interval crosses zero. There is no static-four or matched-budget arm. The local prototype is operationally complete within its audited boundary, while production high availability, physical GPU behavior and the below-15% SLA objective remain unvalidated or unmet.
