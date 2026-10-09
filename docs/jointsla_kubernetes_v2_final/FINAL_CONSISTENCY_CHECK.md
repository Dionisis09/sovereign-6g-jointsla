# Final publication consistency and preservation check

Completed 9 October 2026. **All checks passed.** No existing experimental source or result was edited and no new scientific experiment was executed.

## Common findings across report paper and slides

| Claim | Final value and interpretation |
| --- | --- |
| Main design | 30 paired blocks, 6 arms, 180 trials, 230,400 offered requests |
| JointSLA SLA failures | 49.89 ± 8.12%, mean ± sample SD |
| Core baselines | Reactive 61.43 ± 6.94%; static 61.50 ± 7.85%; HPA 62.39 ± 7.37% |
| Primary effect | JointSLA minus reactive −11.54 pp; 95% paired CI [−13.98, −9.06] |
| Primary significance | Holm p = 3.725290298461914e−08, three-core-comparison family |
| Completed p95 | JointSLA 318.63 ± 47.74 ms; reactive 322.85 ± 55.60 ms; no confirmatory superiority claim |
| HTTP 503 | JointSLA 33.98 ± 7.75%; reactive 43.16 ± 7.48%; all observed main rejections explicitly queue-full |
| Target replica-time | JointSLA 103.45 ± 14.60; reactive 65.12 ± 3.39 replica-seconds |
| Resource trade-off | 58.84% more target replica-time versus reactive, ratio of means; no general resource-efficiency claim |
| Tier failures for JointSLA | Gold 79.63%, Silver 35.94%, Bronze 34.06% |
| Routing ablation | −2.10 pp, CI [−4.84, +0.73], raw exploratory p = 0.158844; effect not established |
| Scaling ablation | −11.05 pp, CI [−13.73, −8.30], raw exploratory p = 3.1478703022003174e−07; feedback prevents unique attribution |
| Historical audits | 1,420 outcomes and 38.83%/47.27% bursts are separate and excluded from main |
| Completion boundary | Local prototype operationally complete; below-15% failure target unmet |

Means, sample standard deviations, tier counts and resource ratios were independently recomputed from the retained CSVs. The publication's all-run and paired-comparison CSVs are byte-identical to the archived frozen originals. Core corrected p-values and percentile intervals retain full precision in the CSV/JSON; display rounding varies only by conventional scientific notation. Native chart caches match canonical means to six decimal places. No rounding changes raw data.

## Preservation

- Evidence archive CRC and every member SHA-256 match the seal: **1,480 files**.
- Original v2, protocol, selected prior reports and frozen source files match the seal: **1,480 files**.
- Original historical result hashes, sizes and timestamps match the seal: **24,364 files**.
- Evidence archive SHA-256: `81462a18af99638c6f7ca68b8688632a71c72ef032eba1017fd5ccf9f5cbc580`.
- The package has a separate `PACKAGE_MANIFEST.json` for final deliverable integrity. The raw archive is a local copy; no independent external backup or public release is claimed.

## Validation and visual review

The unchanged full repository suite passed **330 tests in 32.50 s**, with pytest cache writing disabled. The historical 306/310 counts remain dated audit stages. No tests were added because serving and control implementations were unchanged by this documentation task.

The Word technical report has fourteen pages and the paper draft nine pages. Every page was rendered and visually reviewed. The packaged document renderer could not locate LibreOffice on Windows, so Microsoft Word exported read-only PDFs for private layout inspection and the bundled PDFium runtime rasterized them. Those QA intermediates are not part of the deliverables.

The presentation has fourteen slides, six native editable charts with embedded data workbooks and two native tables. Structural, geometry, font, chart-cache/workbook and first-party import checks passed. Microsoft PowerPoint also opened the final file read-only and exported all fourteen slides for visual review. The final file hash remained unchanged. No clipping or overlap requiring repair remained.

The scripts `validate_publication.py` and `verify_preservation.py` provide repeatable numerical/artifact and archive/original checks. Offline regeneration into a separate scratch directory reproduced all canonical values and tables. Scientific PNGs and vector PDFs use the same canonical means and sample standard deviations. Source references are limited to verified primary publications and official Kubernetes documentation.

## Methodological disclosures retained

Completed-request latency is conditional; all-offered failure denominators retain rejected requests. Core p-values use Holm across three comparisons, while mechanism arms remain exploratory. Resource intervals are additional descriptive analysis with bootstrap seed 271830, not a new experiment or confirmatory test family. Pointwise intervals are not simultaneous coverage guarantees.

The 91.65-minute user pause affects preparation of one exploratory arm before its burst; all trials remain retained, and wall-time metrics include the pause. Kubernetes traffic is a paced deterministic burst rather than the simulator's stochastic arrival model. The held-out simulator and physical CPU serving measurements are distinct. One CPU model, one host, shared resources, native HPA timescales and the absence of a matched-budget arm limit generalization and causal mechanism claims.

The package is ready for research review. Author/affiliation details and venue-specific formatting remain to be supplied before conference submission.
