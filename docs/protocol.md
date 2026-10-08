# Phase 0 protocol (fixed before running)

Synthetic assumptions, not measurements: one tenant, one ingress and gateway,
one inference service with at most two execution targets, two model versions,
one update. Each target starts with one worker and can scale once to two workers.
Only the active target serves new requests; in-flight work finishes on its original
target. The second target exists solely for rerouting. It shares the same ingress
degradation and has 4 ms more path delay, so rerouting cannot magically remove N6
stress. No requests are rejected. Admission ends at 60 s; all admitted requests
are drained. Late requests count against availability.

All policies use one SimPy execution path, identical exogenous workload tapes,
and the same model/network profiles. Model quality is a stipulated score, not a
measured ML accuracy. Service duration is bounded uniform noise about a model
profile. Arrivals are Poisson; network jitter is bounded uniform. Gate predictions
use only current/recent telemetry and declared model profiles, never future
workload/events or future request randomness. No controller sees future events.

The shared local predictor projects recent inference p99 by the service-profile
ratio and capacity ratio, with a current-queue floor. Utilization uses the past
two seconds' arrival rate and declared mean service demand. Independent local
guards check inference and network thresholds, quality, worker availability and
update disruption; they do not sum network and inference latency. Hysteresis
uses 0.8/0.6 utilization and a three-second lifecycle hold. B0 uses a plain local
utilization trigger and scheduled rollout. B1 is the decisive baseline.
CATALYST is B1 plus the four-clause gate: projected network p99 + gateway +
inference p99 must fit the end-to-end bound before a lifecycle action. On a veto,
the same action catalogue permits a scale, safe reroute or rollback fallback.
Local thresholds are intentionally independently permissive, and the end-to-end
sum is conservative; both assumptions limit external validity.

S0: ten seeds, no stress, 10 rps (one quarter of the base workload rate).
The initial 40-rps control proved unhealthy: B0 accumulated 2–5 breach seconds,
and local guards intervened. Those 30 validation runs are preserved separately
in `results/phase0`. Before any stressed run, the S0-only fixture was corrected
to the requested low-load/no-pressure condition. This change is disclosed,
not represented as predeclared in the original protocol or as scientific signal.
All stress values and hypothesis decision rules remain unchanged.
S1/S2/S3: three fixed moderate levels, ten seeds each.
100 matched workload tapes per policy, 300 primary runs. A1 disables composition
and must reproduce B1 exactly. A2 removes the pre-action gate and reacts to
observed breach at the next control tick. Both ablations use the same 100 tapes;
500 total runs. No extra sensitivity matrix or tuning after observing results.

The primary metric is the union of all four contract violations, sampled in
one-second intervals over [0, 60]. Each sample uses completions in the preceding
two-second window. End-to-end latency is empirical p99; quality is the minimum
served quality; availability is timely completions / (completions + outstanding
requests already overdue); update disruption is the longest lifecycle outage
overlapping that window. Empty healthy windows are safe, but overdue requests
and outages still count. A sample at t represents (t-1, t]; sum breached samples
times tick duration, never sum per-clause durations. Results are sampled estimates
of breach time, not exact continuous-time guarantees. Overall p99 and SLA rate
also include completions after admission ends.

Every pre-action veto is audited by deterministic replay forcing that exact action
at that tick and measuring the following two seconds. A false block means this
counterfactual has no observed clause breach in that fixed horizon. This is a
bounded diagnostic, not proof that a blocked action was safe forever. Shadow
outcomes are never fed to the controller. Report local and contract blocks
separately. Action histories include predictions, telemetry and reasons.

Decision: compare paired B1 minus CATALYST breach seconds. Bootstrap seeds
within each level (10,000 resamples; fixed analysis seed). A level qualifies only
with >=5% aggregate reduction, a positive 95% paired difference lower bound,
>=8/10 seeds improved, all rollouts completed, <=10% false contract blocks and
mean completion delay <=one stage hold (3 s) versus B1. A family qualifies with
at least two of three levels qualifying; continue requires two stressed families.
The attribution checks additionally require A1 to equal B1, CATALYST to beat A1
by >=5%, and A2 to lose >=5% relative to B1 breach seconds in qualifying levels.
Strong signal requires >=10% in the qualifying families. Zero B1 breach cannot
support a percentage improvement. S0 must match B1/CATALYST exactly in request
outcomes and lifecycle timing, and all policies must have identical breach seconds.
B0 is explanatory: its aggregate completion time must be within one stage hold
(3 s) and aggregate p99 within 5 ms of the other policies, with all rollouts complete.
The original draft required exact B0 request/lifecycle equality too; the low-load
S0 pilot showed one B0/B1 lifecycle timing outlier (13 s), despite exact B1/CATALYST
behavior and identical all-policy primary outcomes. The criterion was corrected
to the user's **almost identical** control requirement before stressed runs; this
is a disclosed validation correction, not a change to the hypothesis rule.
All runs must conserve requests.
Gains from prolonged action blocking fail the completion-delay rule. Resource
seconds are reported as accounting evidence; a gain from added capacity alone
is not a cost-neutral claim. This decision is for this stipulated simulator only.
