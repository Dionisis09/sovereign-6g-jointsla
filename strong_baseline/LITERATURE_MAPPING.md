# Literature mapping: Myopic Joint Optimization (MJO)

This implementation is literature-inspired and is not claimed to be an exact
reproduction of a specific published algorithm unless explicitly verified.

MJO represents the general constrained joint deployment/allocation and request
assignment formulation: deployment choices alter eligible service replicas and
their current-work completion costs; a resource-coupled binary action program
then chooses reconfiguration under finite CPU/VRAM/bandwidth, lifecycle,
cooldown and action constraints. The physical finite GPU scheduler is unchanged;
GPU compute contention is modeled in the observable candidate cost, rather than
inventing a GPU reservation limit different from the simulator.

The routing subproblem is rectangular min-cost bipartite assignment from
currently waiting requests to ordered replica capacity slots. Additional slot
cost includes backlog, observed mean cycle, resource waiting, network, the
CPU/GPU/CPU pipeline and remaining latency deadline. An SLA-tier-weighted convex
lateness objective is used, rather than a calibrated breach probability.

Scale-out and migration options include the existing cold/downtime penalties,
while allocation and reconfiguration terms discourage gratuitous changes.
All candidate costs use the same current-state matching subproblem. Selection
is global across services under coupled instantaneous reservation headroom;
future release capacity is not borrowed.

SciPy 1.17.1 linear_sum_assignment (local installed implementation/docstring)
solves each matching block exactly. A deterministic specialized budget-two
integer solver searches the deployment menu with valid lower-bound pruning.
Matching is decomposed into oldest-first blocks of 64 for laptop execution;
the complete backlog problem and real stochastic simulation are not claimed
globally optimal. Limit exhaustion is reported and retains the previous state.

No prediction, learning, future arrivals/bursts or hidden service work are used.
The implementation is an independent comparator assembled from this generic
formulation. No paper-specific equation, empirical percentage, literature
performance claim or state-of-the-art claim is imported. Earlier unverified
technical citations and the unrelated radiology reproducibility study do not
justify this optimizer's performance.
