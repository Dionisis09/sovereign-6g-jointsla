# Private GitHub repository

Code, configurations, reports, presentation materials, frozen summaries,
figures, compressed slot/node trajectories and held-out live replay inputs
are included. Python environments, caches, local live runs, secrets, bulk
request/routing/event traces, experiment archives and model weights are
excluded by `.gitignore`. Excluded files remain available locally.

Retained compressed trajectories and replay tapes use ordinary Git; a clone
does not require Git LFS. Research files are not deleted or modified by this
setup. The repository does not include every
raw trace from historical runs; regenerate those with the experiment drivers.

After GitHub authentication and commit identity have been configured:

```powershell
git add .
git commit -m "Add JointSLA research project, dashboard and experimental evidence"
gh repo create sovereign-6g-jointsla --private --source . --remote origin --push
```

To clone with all experiment artifacts:

```powershell
git clone <private-repository-url>
```

Live executions write to ignored `dashboard/.cache/live_runs/`; frozen input
tapes and results remain tracked. Install Python dependencies separately as
documented in the project and dashboard READMEs.
