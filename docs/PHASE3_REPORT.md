# Phase 3 implementation and verification (2026-11-16)

## Scope and provenance

This phase adds an offline-by-default intent parser, optional OpenAI Responses structured output, a packaged versioned lexical knowledge base, and a bounded LangGraph workflow with SQLite checkpoints and separate approval credentials. The only executor is the existing deterministic simulator. The existing JointSLA source and frozen Phase 2 dataset/model/results were not changed. No live LLM request or hardware/cluster action was performed.

## Contracts

- `POST /v1/intents/parse` requires `X-Tenant-Token` and all seven explicit intent fields. English/Greek labels are supported in offline mode. The response identifies `OfflineIntentParser` or `OpenAIIntentParser`.
- `GET /v1/knowledge/search?q=...` filters public and same-tenant documents before lexical scoring. Each result carries source ID, source version, KB version and text. No document text is interpreted as an instruction.
- `POST /v1/workflows` requires `X-Tenant-Token` and `Idempotency-Key`, accepts text and seed, plans through the same deterministic policy gate, and returns `NEEDS_APPROVAL` for a non-no-op. A no-op executes directly in the simulator.
- `POST /v1/workflows/{id}/approve` requires both the tenant operator token and a distinct `X-Approver-Token`. It accepts `{"approved": true|false}`. Approved work resumes from the checkpoint, rechecks freshness/policy and writes one run keyed by workflow ID. Denial creates no run.
- `GET /v1/workflows/{id}` and existing simulation reads are tenant-scoped. SQLite schema migrates from v1 to v2 without replacing prior services/runs.

The OpenAI adapter is enabled only with `SOVEREIGN_LLM_MODE=openai`, `OPENAI_API_KEY`, `SOVEREIGN_LLM_MODEL`, and explicit `SOVEREIGN_LLM_ALLOWED_TENANTS`. Missing key or model uses offline parsing and reports that parser in API output. Unlisted tenants receive 403 before external I/O. The adapter sends only user intent text to `/v1/responses`, uses strict `text.format` JSON schema, `store: false`, ten-second timeout, one retry for invalid output and no retry for transport failure. Strict source-grounding plus Pydantic validation applies after parsing. The model cannot choose tenant identity or bypass policy. API shape follows [OpenAI structured output documentation](https://developers.openai.com/api/docs/guides/structured-outputs). Checkpoint/interrupt design follows [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) and [interrupt documentation](https://docs.langchain.com/oss/python/langgraph/interrupts).

## Tests actually executed

From this Windows Python 3.12 environment:

| Check | Outcome |
| --- | --- |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1; python -m pytest -q tests/test_sovereign_phase3.py` | 19 passed |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1; python -m pytest -q` | 378 passed |
| `python -m ruff check sovereign_maas tests/test_sovereign_maas.py tests/test_sovereign_phase2.py tests/test_sovereign_phase3.py` | passed |
| `python -m ruff format --check` on the same paths | 18 files already formatted |
| `python -m mypy sovereign_maas` | no issues in 15 source files |
| `python -m pip check` | no broken requirements |
| `python -m sovereign_maas.phase3_demo` | `NEEDS_APPROVAL → VERIFIED`, `SIMULATED` verification |
| `python -m pip wheel --no-deps .` and wheel inspection | built; `sovereign_maas/maas_knowledge.json` included |
| GitHub Actions YAML parse | passed |

The Phase 3 tests cover EN/GR labeled intents; missing, extra, impossible and injected fields; mocked structured Responses output, source grounding, one invalid-output retry, transport outage and HTTP 503; tenant authorization before network; KB tenant prefilter and citation provenance; separate approval, denial, restart, idempotency, stale snapshot rejection, no-op and v1→v2 migration. Tests make no external network requests.

Windows Application Control blocks the native `uuid_utils` DLL imported by LangSmith's auto-loaded pytest plugin. Project tests run with pytest plugin autoload disabled; LangGraph itself imported and executed successfully. CI uses the same test setting. No project test was skipped for this reason.

## Limits

The offline parser accepts labeled fields, not unrestricted prose. The KB is a five-document local fixture, so retrieval relevance/faithfulness is not a broad benchmark. Live OpenAI quality, model compatibility, cost, latency, privacy and residency were not validated; only the HTTP contract was exercised with a mock. Checkpointing and business records are in separate local SQLite files; this is durable for the local restart test but not a distributed transaction design. Proposals older than 30 seconds are rejected on approval, and the caller must create a fresh workflow. The existing Phase 2 simulated SLO outcome does not change. No Docker or Kubernetes run was attempted in this phase.
