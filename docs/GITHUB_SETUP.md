# Private GitHub repository

Repository: [Dionisis09/sovereign-6g-jointsla](https://github.com/Dionisis09/sovereign-6g-jointsla) (private).
Start with the [fresh-clone repository guide](../REPOSITORY_GUIDE.md) and the
[organized JointSLA package](../JointSLA/README.md).

Code, configurations, reports, presentation materials, frozen summaries,
figures, compressed slot/node trajectories and held-out live replay inputs
are included. Python environments, caches, local live runs, secrets, bulk
request/routing/event traces, experiment archives and model weights are
excluded by `.gitignore`. Excluded files remain available locally.

Retained compressed trajectories and replay tapes use ordinary Git; a clone
does not require Git LFS. Research files are not deleted or modified by this
setup. The repository does not include every
raw trace from historical runs; regenerate those with the experiment drivers.

To clone the compact project after GitHub authentication:

```powershell
git clone https://github.com/Dionisis09/sovereign-6g-jointsla.git
cd sovereign-6g-jointsla
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-research.txt
.venv\Scripts\python.exe run_dashboard.py
```

This clone contains retained research artifacts, not the complete local raw
archive. Git attributes preserve sealed artifact bytes across platforms, so
automatic newline conversion does not invalidate their hashes.

Live executions write to ignored `dashboard/.cache/live_runs/`; frozen input
tapes and results remain tracked. Install Python dependencies separately as
documented in the project and dashboard READMEs.
