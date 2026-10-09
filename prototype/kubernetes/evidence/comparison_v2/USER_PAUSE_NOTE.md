# User-requested pause: disclosure for comparison v2

On 8 October 2026 the user requested a pause and later explicitly requested resume.
The owned host experiment/pipeline processes were suspended from
21:00:50 to 22:32:29 Europe/Athens (91.65 minutes).
Five completed trials were retained. The pause occurred during the settling phase
of block 0 / joint_sq, after eight direct preconditioning requests per backend
and before any of that arm's offered burst requests.

At resume, process IDs/creation times, frozen source hashes, expected policy,
two ready idle backends and completed preconditioning counters were checked.
Serving containers/controllers remained running; no batch burst ran during pause.
The registered workload, model, policy code, deadlines and repetition count were
not edited. The pause itself lengthens idle time for one exploratory arm and must
be disclosed, rather than claimed to be part of its normal preparation overhead.

The raw `preparation_seconds` and `trial_observed_wall_seconds` fields include
this user pause in the affected trial. They must not be used as unadjusted runner
speed evidence. Burst-request latency/failure fields and burst-to-follow-up
resource integrals start after resume. The pause duration is separately recorded
in `prototype/.cache/kubernetes_comparison_v2/user_pause.json`.

The runner's raw progress ETA also includes paused wall time. An indicative
pause-adjusted ETA uses (elapsed_seconds - user_pause_seconds) / finished times
remaining, rather than interpreting the original ETA as active compute time.
The first block's core JointSLA/reactive/static/HPA measurements were completed
before this pause; the affected joint_sq contrast is registered exploratory.
Any sensitivity analysis excluding that block must be labeled additional,
not substituted silently for the registered 30-block analysis.
