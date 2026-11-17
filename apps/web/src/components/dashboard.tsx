"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type Intent,
  type Model,
  type Monitoring,
  type Research,
  type Run,
  type Service,
  type Workflow,
} from "@/lib/api";

type Section =
  | "overview"
  | "services"
  | "telemetry"
  | "decisions"
  | "execution"
  | "research"
  | "admin";
const sections: { id: Section; label: string; number: string }[] = [
  { id: "overview", label: "Overview", number: "01" },
  { id: "services", label: "Services", number: "02" },
  { id: "telemetry", label: "Telemetry", number: "03" },
  { id: "decisions", label: "Decisions", number: "04" },
  { id: "execution", label: "Execution", number: "05" },
  { id: "research", label: "Research", number: "06" },
  { id: "admin", label: "Admin", number: "07" },
];
const initialIntent: Intent = {
  service_name: "vision-edge-demo",
  tier: "Gold",
  latency_p95_ms: 100,
  minimum_model_quality: 0.9,
  max_replicas: 3,
  allowed_regions: ["eu-gr"],
  allowed_actions: ["noop", "scale_out"],
};

function when(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "Unavailable";
}
function short(value: string) {
  return value.slice(0, 8);
}
function Empty({ children }: { children: React.ReactNode }) {
  return <p className="empty">{children}</p>;
}
function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "good" | "warn";
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
function Panel({
  title,
  kicker,
  children,
}: {
  title: string;
  kicker?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          {kicker && <p className="eyebrow">{kicker}</p>}
          <h2>{title}</h2>
        </div>
      </div>
      {children}
    </section>
  );
}

export default function Dashboard() {
  const [section, setSection] = useState<Section>("overview");
  const [services, setServices] = useState<Service[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [monitoring, setMonitoring] = useState<Monitoring | null>(null);
  const [models, setModels] = useState<Model[]>([]);
  const [research, setResearch] = useState<Research | null>(null);
  const [selectedRun, setSelectedRun] = useState<string>("");
  const [intent, setIntent] = useState<Intent>(initialIntent);
  const [plain, setPlain] = useState("");
  const [seed, setSeed] = useState(42);
  const [serviceId, setServiceId] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    const results = await Promise.allSettled([
      api<Service[]>("services"),
      api<Run[]>("simulations"),
      api<Workflow[]>("workflows"),
      api<Monitoring>("monitoring"),
      api<{ models: Model[] }>("models"),
      api<Research>("research/summary"),
    ]);
    const [
      serviceResult,
      runResult,
      workflowResult,
      monitoringResult,
      modelResult,
      researchResult,
    ] = results;
    setServices(
      serviceResult.status === "fulfilled" ? serviceResult.value : [],
    );
    setRuns(runResult.status === "fulfilled" ? runResult.value : []);
    setWorkflows(
      workflowResult.status === "fulfilled" ? workflowResult.value : [],
    );
    setMonitoring(
      monitoringResult.status === "fulfilled" ? monitoringResult.value : null,
    );
    setModels(
      modelResult.status === "fulfilled" ? modelResult.value.models : [],
    );
    setResearch(
      researchResult.status === "fulfilled" ? researchResult.value : null,
    );
    const failures = results.filter(
      (result) => result.status === "rejected",
    ) as PromiseRejectedResult[];
    setError(
      failures
        .map((result) =>
          result.reason instanceof Error
            ? result.reason.message
            : "Load failed",
        )
        .filter((value, index, array) => array.indexOf(value) === index)
        .join(" · "),
    );
    setLoading(false);
  }, []);

  useEffect(() => {
    queueMicrotask(() => void refresh());
  }, [refresh]);
  const activeRun = runs.find((run) => run.id === selectedRun) ?? runs[0];

  async function mutate(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(success);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="shell">
      <aside className="sidebar" aria-label="Main navigation">
        <div className="brand">
          <div className="brand-mark">
            S<span>6</span>
          </div>
          <div>
            <strong>SOVEREIGN</strong>
            <small>MAAS / CONTROL PLANE</small>
          </div>
        </div>
        <div className="side-label">WORKSPACE</div>
        <nav className="nav-list">
          {sections.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${section === item.id ? "selected" : ""}`}
              onClick={() => setSection(item.id)}
              aria-current={section === item.id ? "page" : undefined}
            >
              <span className="nav-number">{item.number}</span>
              {item.label}
              <span className="nav-arrow">↗</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className="pulse" /> LOCAL SIMULATOR{" "}
          <div className="sidebar-note">
            Tenant scoped · no cluster actuation
          </div>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div>
            <span className="eyebrow">OPERATIONS CONSOLE / PHASE 05</span>
            <h1>{sections.find((item) => item.id === section)?.label}</h1>
          </div>
          <div className="top-actions">
            <Badge tone="warn">SIMULATION ONLY</Badge>
            <button
              className="button button-light"
              onClick={() => void refresh()}
              disabled={loading || busy}
            >
              ↻ Refresh
            </button>
          </div>
        </header>
        {loading && (
          <p className="status" role="status">
            Loading tenant data…
          </p>
        )}
        {error && (
          <div className="alert" role="alert">
            {error}
          </div>
        )}
        {notice && (
          <div className="notice" role="status">
            {notice}
          </div>
        )}

        {section === "overview" && (
          <>
            <div className="hero">
              <div>
                <p className="eyebrow">SYSTEM SNAPSHOT</p>
                <h2>
                  Understand every decision.
                  <br />
                  <em>Verify every outcome.</em>
                </h2>
                <p>
                  Local orchestration view backed by tenant scoped API records.
                  Every run and measurement below is simulated.
                </p>
              </div>
              <div className="hero-art">
                <div className="orbit orbit-one" />
                <div className="orbit orbit-two" />
                <div className="orbit-core">S6</div>
              </div>
            </div>
            <div className="stats">
              <div className="stat">
                <small>SERVICES</small>
                <strong>{services.length}</strong>
                <span>Current page · up to 50</span>
              </div>
              <div className="stat">
                <small>SIMULATION RUNS</small>
                <strong>{runs.length}</strong>
                <span>Current page · up to 50</span>
              </div>
              <div className="stat">
                <small>APPROVAL QUEUE</small>
                <strong>
                  {
                    workflows.filter((item) => item.status === "NEEDS_APPROVAL")
                      .length
                  }
                </strong>
                <span>Current page · up to 50</span>
              </div>
              <div className="stat">
                <small>DRIFT STATUS</small>
                <strong className="stat-word">
                  {monitoring?.drift_status ?? "Unavailable"}
                </strong>
                <span>No live labels</span>
              </div>
            </div>
            <div className="grid-two">
              <Panel title="Recent decisions" kicker="AUDIT TRAIL">
                {runs.length ? (
                  <div className="rows">
                    {runs.slice(0, 5).map((run) => (
                      <button
                        key={run.id}
                        className="row-button"
                        onClick={() => {
                          setSelectedRun(run.id);
                          setSection("decisions");
                        }}
                      >
                        <span>
                          <strong>{short(run.id)}</strong>
                          <small>{when(run.created_at)}</small>
                        </span>
                        <span>{run.decision.selected_candidate_id}</span>
                        <Badge
                          tone={run.verification.slo_met ? "good" : "warn"}
                        >
                          {run.verification.slo_met ? "SLO met" : "SLO missed"}
                        </Badge>
                      </button>
                    ))}
                  </div>
                ) : (
                  <Empty>No simulation runs for this tenant yet.</Empty>
                )}
              </Panel>
              <Panel title="System boundaries" kicker="EVIDENCE">
                {" "}
                <div className="boundary">
                  <span>Execution backend</span>
                  <strong>SIMULATOR</strong>
                </div>
                <div className="boundary">
                  <span>Hardware GPU utilization</span>
                  <strong>Unavailable</strong>
                </div>
                <div className="boundary">
                  <span>Energy proxy</span>
                  <strong>Unavailable</strong>
                </div>
                <div className="boundary">
                  <span>p99 latency</span>
                  <strong>Unavailable</strong>
                </div>
              </Panel>
            </div>
          </>
        )}

        {section === "services" && (
          <div className="grid-two">
            <Panel title="Create service" kicker="TYPED INTENT">
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void mutate(async () => {
                    const result = await api<Service>("intents", intent);
                    setServiceId(result.id);
                  }, "Service created");
                }}
                className="form"
              >
                <label>
                  Service name
                  <input
                    required
                    pattern="[a-z][a-z0-9-]{2,62}"
                    value={intent.service_name}
                    onChange={(event) =>
                      setIntent({ ...intent, service_name: event.target.value })
                    }
                  />
                </label>
                <div className="form-grid">
                  <label>
                    Tier
                    <select
                      value={intent.tier}
                      onChange={(event) =>
                        setIntent({
                          ...intent,
                          tier: event.target.value as Intent["tier"],
                        })
                      }
                    >
                      <option>Gold</option>
                      <option>Silver</option>
                      <option>Bronze</option>
                    </select>
                  </label>
                  <label>
                    p95 target (ms)
                    <input
                      type="number"
                      min="1"
                      max="1000"
                      value={intent.latency_p95_ms}
                      onChange={(event) =>
                        setIntent({
                          ...intent,
                          latency_p95_ms: Number(event.target.value),
                        })
                      }
                    />
                  </label>
                  <label>
                    Min model quality
                    <input
                      type="number"
                      min="0"
                      max="0.95"
                      step="0.01"
                      value={intent.minimum_model_quality}
                      onChange={(event) =>
                        setIntent({
                          ...intent,
                          minimum_model_quality: Number(event.target.value),
                        })
                      }
                    />
                  </label>
                  <label>
                    Max replicas
                    <input
                      type="number"
                      min="1"
                      max="4"
                      value={intent.max_replicas}
                      onChange={(event) =>
                        setIntent({
                          ...intent,
                          max_replicas: Number(event.target.value),
                        })
                      }
                    />
                  </label>
                </div>
                <div className="form-grid">
                  <label>
                    Regions
                    <select
                      value={intent.allowed_regions.join(",")}
                      onChange={(event) =>
                        setIntent({
                          ...intent,
                          allowed_regions: event.target.value.split(","),
                        })
                      }
                    >
                      <option value="eu-gr">eu-gr</option>
                      <option value="eu-gr,eu-de">eu-gr, eu-de</option>
                    </select>
                  </label>
                  <label>
                    Actions
                    <select
                      value={intent.allowed_actions.join(",")}
                      onChange={(event) =>
                        setIntent({
                          ...intent,
                          allowed_actions: event.target.value.split(","),
                        })
                      }
                    >
                      <option value="noop,scale_out">No-op + scale out</option>
                      <option value="noop,scale_out,migrate">
                        All simulated
                      </option>
                      <option value="noop">No-op only</option>
                    </select>
                  </label>
                </div>
                <button className="button button-dark" disabled={busy}>
                  Create service ↗
                </button>
              </form>
              <div className="divider" />
              <p className="eyebrow">PLAIN TEXT PARSER</p>
              <form
                className="form"
                onSubmit={(event) => {
                  event.preventDefault();
                  void mutate(async () => {
                    const parsed = await api<{
                      intent: Intent;
                      parser: string;
                    }>("intents/parse", { text: plain });
                    setIntent(parsed.intent);
                  }, "Parsed intent; review typed fields before creating");
                }}
              >
                <label>
                  Structured labeled text
                  <textarea
                    value={plain}
                    onChange={(event) => setPlain(event.target.value)}
                    placeholder="service_name: vision-edge-demo&#10;tier: Gold&#10;latency_p95_ms: 100&#10;minimum_model_quality: 0.9&#10;max_replicas: 3&#10;allowed_regions: eu-gr&#10;allowed_actions: noop,scale_out"
                    rows={5}
                  />
                </label>
                <button
                  className="button button-light"
                  disabled={busy || !plain.trim()}
                >
                  Parse into form
                </button>
              </form>
            </Panel>
            <Panel title="Tenant services" kicker="CATALOG">
              {services.length ? (
                <div className="rows">
                  {services.map((service) => (
                    <div className="record" key={service.id}>
                      <div>
                        <strong>{service.intent.service_name}</strong>
                        <small>
                          {short(service.id)} · {when(service.created_at)}
                        </small>
                      </div>
                      <Badge>{service.intent.tier}</Badge>
                      <span>{service.intent.latency_p95_ms} ms p95</span>
                      <button
                        className="text-button"
                        onClick={() => {
                          setServiceId(service.id);
                          setSection("execution");
                        }}
                      >
                        Run simulation →
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty>No services yet. Create one with the form.</Empty>
              )}
            </Panel>
          </div>
        )}

        {section === "telemetry" && (
          <>
            <div className="stats">
              <div className="stat">
                <small>LAST SIMULATED p95</small>
                <strong>
                  {activeRun
                    ? activeRun.snapshot.observed_p95_ms.toFixed(1)
                    : "—"}
                  <span className="unit"> ms</span>
                </strong>
                <span>
                  {activeRun
                    ? when(activeRun.snapshot.observed_at)
                    : "No snapshot"}
                </span>
              </div>
              <div className="stat">
                <small>ARRIVAL RATE</small>
                <strong>
                  {activeRun ? activeRun.snapshot.arrival_rps.toFixed(1) : "—"}
                  <span className="unit"> rps</span>
                </strong>
                <span>Simulated workload</span>
              </div>
              <div className="stat">
                <small>QUEUE DEPTH</small>
                <strong>{activeRun?.snapshot.queue_depth ?? "—"}</strong>
                <span>Simulated workload</span>
              </div>
              <div className="stat">
                <small>SAMPLE FRESHNESS</small>
                <strong className="stat-word">
                  {activeRun ? "Historical" : "Unavailable"}
                </strong>
                <span>
                  {activeRun
                    ? when(activeRun.snapshot.observed_at)
                    : "No snapshot"}
                </span>
              </div>
            </div>
            <Panel title="Simulated p95 timeline" kicker="LAST 50 RUNS">
              {runs.length ? (
                <div
                  className="chart"
                  role="img"
                  aria-label="Simulated observed p95 latency by recent run"
                >
                  {runs
                    .slice()
                    .reverse()
                    .map((run) => (
                      <div
                        key={run.id}
                        className="chart-column"
                        title={`${run.snapshot.observed_p95_ms.toFixed(1)} ms · ${when(run.snapshot.observed_at)}`}
                      >
                        <div
                          className="chart-bar"
                          style={{
                            height: `${Math.max(4, Math.min(100, run.snapshot.observed_p95_ms / 2))}%`,
                          }}
                        />
                        <small>{short(run.id)}</small>
                      </div>
                    ))}
                </div>
              ) : (
                <Empty>
                  No telemetry snapshots yet. Run a simulation to create one.
                </Empty>
              )}
              <p className="caption">
                Bars show observed p95 from seeded simulator snapshots. Scale:
                200 ms fills the plot; values above 200 ms are clipped visually.
                This is historical simulation output, not a live stream.
              </p>
            </Panel>
            <div className="grid-two">
              <Panel title="Unavailable signals" kicker="DATA CONTRACT">
                <div className="boundary">
                  <span>p99 latency</span>
                  <strong>No source</strong>
                </div>
                <div className="boundary">
                  <span>GPU utilization</span>
                  <strong>No hardware</strong>
                </div>
                <div className="boundary">
                  <span>Throughput</span>
                  <strong>No measurement</strong>
                </div>
                <div className="boundary">
                  <span>Energy proxy</span>
                  <strong>No measurement</strong>
                </div>
              </Panel>
              <Panel title="Monitoring" kicker="EVALUATION">
                {monitoring ? (
                  <>
                    <div className="boundary">
                      <span>Recent simulations</span>
                      <strong>
                        {monitoring.recent_run_count} /{" "}
                        {monitoring.window_limit}
                      </strong>
                    </div>
                    <div className="boundary">
                      <span>Forecast coverage</span>
                      <strong>
                        {monitoring.forecast_coverage === null
                          ? "Unavailable"
                          : `${(monitoring.forecast_coverage * 100).toFixed(1)}%`}
                      </strong>
                    </div>
                    <div className="boundary">
                      <span>Simulated SLO rate</span>
                      <strong>
                        {monitoring.simulated_slo_rate === null
                          ? "Unavailable"
                          : `${(monitoring.simulated_slo_rate * 100).toFixed(1)}%`}
                      </strong>
                    </div>
                    <div className="boundary">
                      <span>Drift</span>
                      <strong>{monitoring.drift_status}</strong>
                    </div>
                    <p className="caption">{monitoring.drift_reason}</p>
                  </>
                ) : (
                  <Empty>Monitoring endpoint unavailable.</Empty>
                )}
              </Panel>
            </div>
          </>
        )}

        {section === "decisions" && (
          <>
            <Panel title="Decision inspector" kicker="POLICY TRACE">
              <label className="select-label">
                Simulation run
                <select
                  value={activeRun?.id ?? ""}
                  onChange={(event) => setSelectedRun(event.target.value)}
                >
                  {runs.map((run) => (
                    <option key={run.id} value={run.id}>
                      {short(run.id)} · {when(run.created_at)}
                    </option>
                  ))}
                </select>
              </label>
              {activeRun ? (
                <>
                  <div className="decision-head">
                    <div>
                      <span className="eyebrow">SELECTED CANDIDATE</span>
                      <h3>{activeRun.decision.selected_candidate_id}</h3>
                      <p>
                        {activeRun.decision.status} · policy correlation{" "}
                        {short(activeRun.decision.correlation_id)}
                      </p>
                    </div>
                    <Badge
                      tone={activeRun.verification.slo_met ? "good" : "warn"}
                    >
                      {activeRun.verification.slo_met
                        ? "SIMULATED SLO MET"
                        : "SIMULATED SLO MISSED"}
                    </Badge>
                  </div>
                  <div className="grid-two">
                    <div>
                      <h3 className="subhead">Candidates & policy</h3>
                      {activeRun.candidates.map((candidate) => {
                        const rejection = activeRun.decision.rejected.find(
                          (item) => item.candidate_id === candidate.id,
                        );
                        return (
                          <div className="candidate" key={candidate.id}>
                            <div>
                              <strong>{candidate.id}</strong>
                              <Badge
                                tone={
                                  candidate.id ===
                                  activeRun.decision.selected_candidate_id
                                    ? "good"
                                    : "neutral"
                                }
                              >
                                {candidate.kind}
                              </Badge>
                            </div>
                            <small>
                              {candidate.target_node} ·{" "}
                              {candidate.target_replicas} replicas · rule
                              post-p95 {candidate.post_p95_rule_ms.toFixed(1)}{" "}
                              ms
                            </small>
                            <p>
                              {rejection
                                ? `Rejected: ${rejection.reasons.join("; ")}`
                                : "No rejection recorded"}
                            </p>
                          </div>
                        );
                      })}
                    </div>
                    <div>
                      <h3 className="subhead">Forecast & advisory</h3>
                      <div className="boundary">
                        <span>Model</span>
                        <strong>
                          {activeRun.forecast?.model_version ??
                            "No trained predictor"}
                        </strong>
                      </div>
                      <div className="boundary">
                        <span>Breach probability / 12s</span>
                        <strong>
                          {activeRun.forecast
                            ? `${(activeRun.forecast.breach_probability_12s * 100).toFixed(1)}%`
                            : "Unavailable"}
                        </strong>
                      </div>
                      <div className="boundary">
                        <span>TTV q10</span>
                        <strong>
                          {activeRun.forecast?.ttv_q10_s ?? "Unavailable"}
                        </strong>
                      </div>
                      <div className="boundary">
                        <span>Jev advisory</span>
                        <strong>
                          {activeRun.judgment
                            ? `${activeRun.judgment.source} / ${activeRun.judgment.status}`
                            : "Unavailable"}
                        </strong>
                      </div>
                      <p className="caption">
                        {activeRun.judgment?.reason ??
                          "Advisory cannot override deterministic policy."}
                      </p>
                      <h3 className="subhead">Policy reasons</h3>
                      <ul className="reason-list">
                        {activeRun.decision.reasons.map((reason, index) => (
                          <li key={index}>{reason}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </>
              ) : (
                <Empty>No decisions yet. Run a simulation first.</Empty>
              )}
            </Panel>
          </>
        )}

        {section === "execution" && (
          <div className="grid-two">
            <div>
              <Panel title="Run simulation" kicker="CONTROLLED EXECUTION">
                <form
                  className="form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void mutate(
                      () =>
                        api("simulations/run", { service_id: serviceId, seed }),
                      "Simulation completed",
                    );
                  }}
                >
                  <label>
                    Service
                    <select
                      required
                      value={serviceId}
                      onChange={(event) => setServiceId(event.target.value)}
                    >
                      <option value="">Choose a service</option>
                      {services.map((service) => (
                        <option key={service.id} value={service.id}>
                          {service.intent.service_name} ({short(service.id)})
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Seed
                    <input
                      type="number"
                      min="0"
                      max="1000000"
                      value={seed}
                      onChange={(event) => setSeed(Number(event.target.value))}
                    />
                  </label>
                  <button
                    className="button button-dark"
                    disabled={busy || !serviceId}
                  >
                    Execute in simulator ↗
                  </button>
                </form>
              </Panel>
              <Panel title="Start workflow" kicker="PLAIN INTENT + HITL">
                <form
                  className="form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void mutate(
                      () => api("workflows", { text: plain, seed }),
                      "Workflow started",
                    );
                  }}
                >
                  <label>
                    Labeled intent
                    <textarea
                      rows={5}
                      value={plain}
                      onChange={(event) => setPlain(event.target.value)}
                      placeholder="Paste labeled fields from Services"
                    />
                  </label>
                  <button
                    className="button button-light"
                    disabled={busy || !plain.trim()}
                  >
                    Start workflow
                  </button>
                </form>
              </Panel>
            </div>
            <Panel title="Execution timeline" kicker="SIMULATED RUNS">
              {runs.length ? (
                <div className="rows">
                  {runs.map((run) => (
                    <div className="record" key={run.id}>
                      <div>
                        <strong>
                          {short(run.id)} · seed {run.seed}
                        </strong>
                        <small>
                          {when(run.created_at)} ·{" "}
                          {services.find(
                            (service) => service.id === run.service_id,
                          )?.intent.service_name ?? short(run.service_id)}
                        </small>
                      </div>
                      <Badge tone={run.verification.slo_met ? "good" : "warn"}>
                        {run.verification.slo_met
                          ? "Verified SLO"
                          : "Missed SLO"}
                      </Badge>
                      <span>
                        {run.verification.measured_p95_ms.toFixed(1)} ms ·{" "}
                        {run.verification.evidence}
                      </span>
                      <button
                        className="text-button"
                        onClick={() => {
                          setSelectedRun(run.id);
                          setSection("decisions");
                        }}
                      >
                        Inspect →
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty>No simulation executions yet.</Empty>
              )}
            </Panel>
          </div>
        )}

        {section === "research" && (
          <>
            <div className="hero hero-small">
              <div>
                <p className="eyebrow">REPRODUCIBLE EVIDENCE</p>
                <h2>
                  Research, with its
                  <br />
                  <em>limits in view.</em>
                </h2>
                <p>
                  Read directly from checked local Phase 2 and Phase 4 metrics
                  files. No dashboard generated claims.
                </p>
              </div>
            </div>
            {research ? (
              <div className="grid-two">
                <Panel
                  title="Phase 2 · trained baseline"
                  kicker="SIMULATION ONLY"
                >
                  {(() => {
                    const data = research.summaries["phase2-v1"] as
                      | {
                          breach?: {
                            calibrated_logistic?: {
                              brier?: number;
                              auroc?: number;
                              n?: number;
                            };
                          };
                          decision?: {
                            simulated_slo_rate_selected?: number;
                            simulated_slo_rate_noop?: number;
                            n?: number;
                          };
                          model_sha256?: string;
                          test_seed_range?: number[];
                        }
                      | undefined;
                    return data ? (
                      <>
                        <div className="research-metric">
                          <small>BREACH BRIER</small>
                          <strong>
                            {data.breach?.calibrated_logistic?.brier?.toFixed(
                              4,
                            ) ?? "—"}
                          </strong>
                        </div>
                        <div className="boundary">
                          <span>AUROC</span>
                          <strong>
                            {data.breach?.calibrated_logistic?.auroc?.toFixed(
                              3,
                            ) ?? "—"}
                          </strong>
                        </div>
                        <div className="boundary">
                          <span>Selected / no-op simulated SLO</span>
                          <strong>
                            {data.decision?.simulated_slo_rate_selected ?? "—"}{" "}
                            / {data.decision?.simulated_slo_rate_noop ?? "—"}
                          </strong>
                        </div>
                        <p className="caption">
                          n={data.decision?.n}; seeds{" "}
                          {data.test_seed_range?.join("–")}; model SHA-256{" "}
                          {data.model_sha256?.slice(0, 16)}…
                        </p>
                      </>
                    ) : (
                      <Empty>Phase 2 artifact unavailable.</Empty>
                    );
                  })()}
                </Panel>
                <Panel
                  title="Phase 4 · advisory comparison"
                  kicker="FIXTURE PROXY, NOT JEV"
                >
                  {(() => {
                    const data = research.summaries["phase4-v1"] as
                      | {
                          classic_ml?: {
                            simulated_slo_rate?: number;
                            breach_brier?: number;
                          };
                          fixture_only?: {
                            simulated_slo_rate?: number;
                            breach_brier_uncalibrated_proxy?: number;
                          };
                          live_jev_accuracy?: number | null;
                          n_episodes?: number;
                          test_seed_range?: number[];
                        }
                      | undefined;
                    return data ? (
                      <>
                        <div className="research-metric">
                          <small>CLASSIC ML / FIXTURE SLO</small>
                          <strong>
                            {data.classic_ml?.simulated_slo_rate ?? "—"} /{" "}
                            {data.fixture_only?.simulated_slo_rate ?? "—"}
                          </strong>
                        </div>
                        <div className="boundary">
                          <span>ML Brier / fixture proxy</span>
                          <strong>
                            {data.classic_ml?.breach_brier?.toFixed(4) ?? "—"} /{" "}
                            {data.fixture_only
                              ?.breach_brier_uncalibrated_proxy ?? "—"}
                          </strong>
                        </div>
                        <div className="boundary">
                          <span>Live Jev accuracy</span>
                          <strong>
                            {data.live_jev_accuracy ?? "Unmeasured"}
                          </strong>
                        </div>
                        <p className="caption">
                          n={data.n_episodes}; seeds{" "}
                          {data.test_seed_range?.join("–")}. The fixture did not
                          improve the simulated SLO rate.
                        </p>
                      </>
                    ) : (
                      <Empty>Phase 4 artifact unavailable.</Empty>
                    );
                  })()}
                </Panel>
              </div>
            ) : (
              <Panel title="Research evidence" kicker="ARTIFACTS">
                <Empty>
                  Research artifacts are not mounted or the API is unavailable.
                </Empty>
              </Panel>
            )}
          </>
        )}

        {section === "admin" && (
          <div className="grid-two">
            <Panel title="Approval queue" kicker="SEPARATE CREDENTIAL">
              {workflows.filter((item) => item.status === "NEEDS_APPROVAL")
                .length ? (
                <div className="rows">
                  {workflows
                    .filter((item) => item.status === "NEEDS_APPROVAL")
                    .map((item) => (
                      <div className="record" key={item.id}>
                        <div>
                          <strong>{short(item.id)}</strong>
                          <small>{item.reason ?? "Approval requested"}</small>
                        </div>
                        <button
                          className="button button-light"
                          disabled={busy}
                          onClick={() =>
                            void mutate(
                              () =>
                                api(`workflows/${item.id}/approve`, {
                                  approved: true,
                                }),
                              "Workflow approved",
                            )
                          }
                        >
                          Approve
                        </button>
                        <button
                          className="button button-light"
                          disabled={busy}
                          onClick={() =>
                            void mutate(
                              () =>
                                api(`workflows/${item.id}/approve`, {
                                  approved: false,
                                }),
                              "Workflow rejected",
                            )
                          }
                        >
                          Reject
                        </button>
                      </div>
                    ))}
                </div>
              ) : (
                <Empty>No workflows awaiting approval.</Empty>
              )}
              <p className="caption">
                Approval requires a distinct server-side approver token.
              </p>
            </Panel>
            <Panel title="Model registry" kicker="GATED SHADOW REVIEW">
              {models.length ? (
                models.map((model) => (
                  <div key={model.model_sha256}>
                    <div className="boundary">
                      <span>Version</span>
                      <strong>{model.model_version}</strong>
                    </div>
                    <div className="boundary">
                      <span>Stage</span>
                      <strong>{model.stage}</strong>
                    </div>
                    <div className="boundary">
                      <span>Runtime</span>
                      <strong>{model.runtime}</strong>
                    </div>
                    <div className="boundary">
                      <span>Artifact validated</span>
                      <strong>
                        {model.artifact_validated_at_startup
                          ? "At startup"
                          : "No"}
                      </strong>
                    </div>
                    <div className="boundary">
                      <span>Approved at</span>
                      <strong>{when(model.approved_at)}</strong>
                    </div>
                    <button
                      className="button button-dark"
                      disabled={busy || model.stage === "APPROVED_SHADOW"}
                      onClick={() =>
                        void mutate(
                          () =>
                            api(
                              `models/${model.model_version}/promote-shadow`,
                              {},
                            ),
                          "Model approved for shadow review",
                        )
                      }
                    >
                      Approve shadow stage
                    </button>
                    <p className="caption">
                      This records review only. It does not activate or replace
                      the configured predictor.
                    </p>
                  </div>
                ))
              ) : (
                <Empty>
                  No trained model configured. Set SOVEREIGN_MODEL_DIR on the
                  API.
                </Empty>
              )}
            </Panel>
          </div>
        )}
        <footer className="footer">
          <span>SOVEREIGN MAAS · LOCAL RESEARCH SYSTEM</span>
          <span>
            Data: simulated · decisions: deterministic · actuation: none
          </span>
        </footer>
      </main>
    </div>
  );
}
