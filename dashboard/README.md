# JointSLA research dashboard

Local Streamlit + Plotly presentation of completed research, with a separate live simulation view. English scientific content, large presentation views and plain-language teaching explanations. Frozen evidence remains read-only; live runs use unchanged engines and archived inputs.

From the repository root on Windows:

```powershell
.venv\Scripts\python.exe -m pip install -r dashboard/requirements.txt
.venv\Scripts\python.exe run_dashboard.py
```

Alternative:

```powershell
.venv\Scripts\streamlit.exe run dashboard/app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Open http://127.0.0.1:8501. Stop with Ctrl+C. Generic environments can use `pip install -r dashboard/requirements.txt` and `streamlit run dashboard/app.py`. NumPy and pandas already belong to the main environment; only Streamlit and Plotly are added here. Main requirement files are unchanged.

## Views and controls

21 navigation views: Overview; System & JointSLA; Synthetic Results; Scalability; Controller Optimization; Strong Baseline; Hardware Profiling; Hardware-Grounded Reversal; Pressure Sweep; Tier Behavior; Model Class Behavior; Mechanism Analysis; Burst Recovery; JointSLA-v2; v2 Held-out Results; Performance–Resource Trade-off; SOVEREIGN / Intent; Experiment Timeline; Research Story; Data / Reproducibility; Live Experiments. QoS, resources and seed explorer are supporting tabs within comparative views.

Controls appear only in the applicable scope: policy, scale, load, metric, tier, class, model, measured statistic and seed. Across-load graphs retain the complete load series; the selected load scopes metric cards, source rows and the associated statistical details. Seed selection changes inspected rows, while distributions explicitly retain all selected run seeds. Presentation Mode enlarges charts/fonts and keeps long context collapsed. Learning Mode offers 11 expandable explanations. The system sliders are explicitly illustrative arithmetic, not experimental evidence or a simulator run.

Original verified figures and reports remain available through expanders. Source inspection and CSV download use the same filtered frame. Plotly supports hover, legend isolation, zoom and PNG export. No download writes into research directories.

## Architecture

- `data_loader.py`: discovered paths, cached read-only CSV/text/JSON reads, optional-file fallback and guard against huge defaults.
- `metrics.py`: policy display labels, explicit unit conversions, adaptations of frozen paired-statistic schemas.
- `charts.py`: shared Plotly theme, asymmetric existing CIs, seed distributions and descriptive operating points.
- `components.py`: cards, provenance, CSV download, explanations and diagrams.
- `data_validation.py`: small-summary schema/key/seed/hash validation.
- `styles.py`: local dark technical theme.
- `app.py`: scoped UI and scientific narrative.
- `live_experiments.py`: isolated real executions, archived-input restoration, physical audits and frozen metric comparisons.
- `live_page.py`: live-run form, fresh metrics, latency/queue/GPU trajectories and downloads.
- `run_dashboard.py`: local Streamlit launcher, using the active interpreter.

The browser is presentation state only. Loaders use Streamlit memory cache and make no source writes. Validation warns instead of repairing sources. Optional missing evidence displays an unavailable panel. Missing metrics are not substituted or extrapolated. No request-level data are loaded by default. Existing frozen confidence intervals, Holm-adjusted tests and effect sizes remain authoritative; no new bootstrap or statistical tests run in the dashboard.

See [DATA_SOURCES.md](DATA_SOURCES.md), [CLAIMS.md](CLAIMS.md), and [SUPERVISOR_DEMO.md](SUPERVISOR_DEMO.md). Verification details live in `dashboard/.cache/verification.json` after local QA; this is a presentation artifact, not scientific evidence.

## Live execution

Select **Live Experiments**, choose hardware-grounded load 1× or 2×, one to three archived seeds from 31–60, and SLA-aware / JointSLA-v1 / JointSLA-v2. Click **Run live paired experiment**. Each policy executes the actual simulator anew using identical input tapes. This is simulated infrastructure using hardware-derived profiles, not real GPU inference or deployment.

Outputs are unique directories under `dashboard/.cache/live_runs/`. Each includes request outcomes, slot/node trajectories, actions and lifecycle records, metrics CSV, frozen comparison CSV and a provenance/audit manifest. Exported outcomes are verified against in-memory outcomes. Physical/accounting audits, workload hashes and frozen source hashes are checked. Ten scientific metrics are compared with the same archived seed/policy; execution times may vary.

The page exposes fresh result comparisons, latency, cumulative SLA failures, queue depth and GPU utilization, plus metrics and manifest downloads. No arrivals are generated, parameters tuned or paper statistics updated. A replay supports repeatability for selected cases; the frozen paired 30-seed analysis remains the statistical evidence.
