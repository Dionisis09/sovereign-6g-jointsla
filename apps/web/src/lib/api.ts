export type Intent = {
  service_name: string;
  tier: "Gold" | "Silver" | "Bronze";
  latency_p95_ms: number;
  minimum_model_quality: number;
  max_replicas: number;
  allowed_regions: string[];
  allowed_actions: string[];
};
export type Service = {
  id: string;
  created_at: string;
  intent: Intent;
  model_id: string;
  evidence: string;
};
export type Candidate = {
  id: string;
  kind: string;
  target_node: string;
  target_replicas: number;
  ttr_high_s: number;
  post_p95_rule_ms: number;
};
export type Run = {
  id: string;
  service_id: string;
  created_at: string;
  seed: number;
  snapshot: {
    observed_at: string;
    observed_p95_ms: number;
    arrival_rps: number;
    queue_depth: number;
    evidence: string;
  };
  candidates: Candidate[];
  decision: {
    status: string;
    selected_candidate_id: string;
    reasons: string[];
    rejected: { candidate_id: string; reasons: string[] }[];
    model_version: string | null;
    correlation_id: string;
  };
  verification: {
    measured_p95_ms: number;
    slo_met: boolean;
    final_node: string;
    final_replicas: number;
    evidence: string;
  };
  forecast: {
    model_version: string;
    evidence: string;
    breach_probability_12s: number;
    ttv_q10_s: number | null;
    ttr_q90_s: Record<string, number>;
    post_sla_probability: Record<string, number>;
  } | null;
  judgment: {
    source: string;
    status: string;
    model_version: string | null;
    reason: string | null;
    review_probability: number | null;
  } | null;
};
export type Workflow = {
  id: string;
  status: string;
  service_id: string | null;
  run_id: string | null;
  reason: string | null;
  citations: string[];
  selected_candidate_id: string | null;
};
export type Monitoring = {
  evidence: string;
  recent_run_count: number;
  window_limit: number;
  latest_run_at: string | null;
  forecast_coverage: number | null;
  simulated_slo_rate: number | null;
  drift_status: string;
  drift_reason: string;
};
export type Model = {
  model_sha256: string;
  model_version: string;
  stage: string;
  runtime: string;
  approved_at: string | null;
  artifact_validated_at_startup: boolean;
};
export type Research = { source: string; summaries: Record<string, unknown> };

export async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/maas/${path}`, {
    method: body === undefined ? "GET" : "POST",
    cache: "no-store",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    const error = payload as { detail?: unknown };
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : `Request failed (${response.status})`,
    );
  }
  return payload as T;
}
