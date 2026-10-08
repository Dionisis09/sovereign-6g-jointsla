# Repository audit, before implementation

Audit date: 2026-10-06. Workspace: `C:/Users/dioni/Documents/ChatGPT/6g`.
The repository contained only `.git`, with no commits, branches with content,
remotes, source files, or AGENTS.md. The parent ChatGPT directory contained only
this workspace. The user was asked for the prior AIMCO/VISTA repository location.
The user subsequently identified the previous chat as **6g 1**. Its files are at
`C:/Users/dioni/Documents/Codex/2026-10-06/kan/outputs`; that directory is not a
Git repository. The new branch remains in the user-provided current repository,
and the old artifacts are read-only references. No prior scientific assumptions,
objectives, tuning, or claims are imported.

## Existing code reusable

Extracted verbatim into `catalyst/reused.py`:

* AIMCO Phase 1 `aimco6g/runner.py`: `jsonable`, `digest` (serialization and replay hash).
* VISTA Phase 0 `vista6g/evaluation.py`: `quantile` (linear empirical quantile).
* VISTA Phase 0 `vista6g/experiments.py`: `write_json`, `write_gzip` (strict JSON
  and gzip logging with fixed modification time).

Exact source paths, hashes, names, and adaptations are in `reuse-provenance.json`.
These are user-owned local code; no third-party source notice was found in them.
The quantile is independently checked against NumPy, and replay/output helpers
are tested anew. Prior tests are evidence to inspect, not validation inherited
automatically by extraction.

Audited but not imported wholesale: AIMCO `core.py`, `resources.py`, `sla.py`,
`simulation.py`, `scenarios.py`; VISTA `model.py`, `simulator.py`, `scenarios.py`,
`analysis.py`, and `tests/test_vista.py`. They couple generic operations to old
multi-resource reservations, three sites, session stickiness, model transfer,
or hypothesis-specific metrics. SimPy replaces their custom event scheduler;
immutable workload tapes, public observations, paired request IDs and seed-level
analysis retain their validated engineering patterns. New workload rates, network
profiles, lifecycle and thresholds are independently declared in this protocol.

## Available dependencies

The default Python 3.14 environment had none of the requested scientific packages.
The bundled Python 3.12 environment already provided Pydantic 2.13.5, NumPy 2.3.5,
and pandas 3.0.1. SimPy, matplotlib, and pytest were absent; they are installed
in a workspace-local virtual environment inheriting the bundled packages.
No libraries are installed into the user's global Python environments.

Reuse: SimPy scheduling and FIFO resource queues; Pydantic validation and JSON
schema; NumPy random streams, quantiles and paired bootstrap; pandas CSV/grouped
analysis; matplotlib plots; pytest tests. Standard library: dataclasses, enum,
hashlib, JSON, gzip, argparse, pathlib, importlib.metadata, subprocess.

No external third-party source code is copied. Dependencies retain their upstream licenses:
SimPy MIT, Pydantic MIT, NumPy BSD-3-Clause, pandas BSD-3-Clause, matplotlib PSF-
based license, pytest MIT. Consult installed distribution metadata for licenses.

## New modules required

* `catalyst/contracts.py`: four-clause structured intent and compiler.
* `catalyst/scenario.py`: minimal scenario/event configuration and frozen workload.
* `catalyst/engine.py`: application model using SimPy; shared local protection and
  the additional cross-layer action gate. No simulation framework is invented.
* `catalyst/experiment.py`: fixed paired matrix, counterfactual false-block audit,
  paired analysis and decision rule using existing analysis libraries.
* `tests/test_phase0.py`: contract, replay, boundary and mechanism fixtures.

## Deliberately omitted

Multi-tenancy, autonomous agents, Kubernetes, OpenNebula, RL, digital twins,
additional baselines, additional ablations, real infrastructure integrations,
bandwidth/placement policy languages, and scenario-specific simulators.

## Upstream implementation references

* [SimPy shared resources](https://simpy.readthedocs.io/en/stable/simpy_intro/shared_resources.html)
* [Pydantic configuration](https://docs.pydantic.dev/latest/api/config/)

