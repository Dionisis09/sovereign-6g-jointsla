# JointSLA-v2: final controlled algorithmic experiment

This separate controller wraps the unchanged hardware-grounded simulator. It
keeps v1 routing, rejects scale-ins below causal warm headroom and establishes
a finite Gold floor when capacity and the original two-action budget permit.
See PLAN.md for the complete predeclared formula, engineering gates, statistical
families, hypothesis criteria and stop rule. One candidate only; no forecasting.

Dependencies are the existing requirements.txt and requirements-paper.txt;
simulation requires no new GPU profiling. Run from the repository root:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe run_jointsla_v2.py --development
.venv\Scripts\python.exe run_jointsla_v2.py --freeze
.venv\Scripts\python.exe run_jointsla_v2.py --held-out
```

Development uses only seeds101–105 at0.5/1/2x (45 runs). Held-out uses31–60 at1/2x
(180 runs). Both pair SLA-aware, v1 and v2 on identical arrival tapes. The seed
gate runs before workload generation. Freeze requires the engineering gate and
checks historical file hashes. The freeze records parameter/source hashes,
UTC time, git status and the generation-ledger audit. Held-out refuses modified
source/config/algorithm-description files. No editing or retuning after freeze.

Use --reuse-results to independently recheck and regenerate analytical artifacts
without simulations; --force replays the same frozen runs and preserves the
generation ledger. Do not use either option to change the design. Outputs are
separate results/jointsla_v2_development and results/jointsla_v2_heldout trees.
Every request, resource/lifecycle event, routing choice and slot trajectory is
exported; headroom_results.csv has v2 service/slot observations. Runtime fields
vary by host; semantic outcomes and bootstrap streams are deterministic.

Read report.md and hypothesis_assessment.json regardless of result. Development
statistics are engineering diagnostics only. The full held-out study ends the
algorithmic phase: no v3 and no more large scheduling experiments.
