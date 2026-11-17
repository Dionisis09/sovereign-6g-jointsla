"""Transparent NumPy baselines and checked JSON model artifacts."""

import hashlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .domain import (
    ActionKind,
    CandidateAction,
    ForecastBundle,
    ServiceBundle,
    TelemetrySnapshot,
    TopologyNode,
    TypedIntent,
)
from .research_data import SPLIT_PATH, sha256, split_plan

FEATURES = ("queue_depth", "arrival_rps", "cycle_ms", "network_ms", "slo_ms", "headroom_ms")
HORIZON = 12


def episode_matrix(frame: pd.DataFrame) -> np.ndarray:
    return frame.loc[:, FEATURES].to_numpy(dtype=float)


def action_matrix(frame: pd.DataFrame) -> np.ndarray:
    base = episode_matrix(frame)
    kinds = frame["action_kind"].to_numpy()
    one_hot = np.column_stack([kinds == kind for kind in ("scale_out", "migrate", "noop")]).astype(float)
    targets = frame[["target_replicas", "target_network_ms"]].to_numpy(dtype=float)
    return np.column_stack((base, one_hot, targets))


def hazard_matrix(frame: pd.DataFrame, training: bool) -> tuple[np.ndarray, np.ndarray | None]:
    rows: list[list[float]] = []
    labels: list[int] = []
    for record in frame.itertuples(index=False):
        features = [float(getattr(record, name)) for name in FEATURES]
        limit = int(record.followup_s) if training else HORIZON
        for tick in range(1, limit + 1):
            rows.append([*features, float(tick)])
            if training:
                labels.append(int(not record.ttv_censored and record.ttv_observed_s == tick))
    return np.asarray(rows, dtype=float), np.asarray(labels, dtype=int) if training else None


def validate_frames(episodes: pd.DataFrame, actions: pd.DataFrame) -> None:
    plan = split_plan()
    if len(episodes) != 500 or len(actions) != 1500:
        raise ValueError("unexpected replay row count")
    if not episodes["episode_id"].is_unique:
        raise ValueError("duplicate episodes")
    if episodes["observed_p95_ms"].ge(episodes["slo_ms"]).any():
        raise ValueError("TTV dataset must start healthy")
    for split in ("train", "validation", "test"):
        subset = episodes[episodes["split"] == split]
        if set(subset["seed"]) != set(plan[f"{split}_seeds"]):
            raise ValueError("seed split drift")
        if len(subset) != len(plan[f"{split}_seeds"]) * len(plan["scenario_families"]):
            raise ValueError("missing scenario episode")
    merged = actions.merge(
        episodes[["episode_id", "split"]], on="episode_id", suffixes=("", "_episode"), validate="many_to_one"
    )
    if len(merged) != len(actions) or (merged["split"] != merged["split_episode"]).any():
        raise ValueError("action and episode split mismatch")
    if episodes.loc[episodes["ttv_censored"], "ttv_observed_s"].notna().any():
        raise ValueError("censored TTV must be missing")
    if episodes.loc[~episodes["ttv_censored"], "ttv_observed_s"].isna().any():
        raise ValueError("observed breach requires TTV")
    if not np.isfinite(episode_matrix(episodes)).all():
        raise ValueError("nonfinite features")


def load_frames(output: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    manifest = json.loads((output / "dataset_manifest.json").read_text(encoding="utf-8"))
    if manifest["split_sha256"] != sha256(SPLIT_PATH):
        raise RuntimeError("split manifest mismatch")
    if manifest["generator_sha256"] != sha256(Path(__file__).with_name("research_data.py")):
        raise RuntimeError("replay generator changed")
    for name, digest in manifest["files"].items():
        if sha256(output / name) != digest:
            raise RuntimeError(f"dataset checksum mismatch: {name}")
    episodes = pd.read_parquet(output / "episodes.parquet")
    actions = pd.read_parquet(output / "actions.parquet")
    validate_frames(episodes, actions)
    return episodes, actions, manifest


def joined_actions(episodes: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
    return actions.merge(episodes[["episode_id", *FEATURES]], on="episode_id", validate="many_to_one")


def _design(x: np.ndarray, mean: np.ndarray, scale: np.ndarray) -> np.ndarray:
    return np.column_stack((np.ones(len(x)), (x - mean) / scale))


def _sigmoid(logits: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(logits, -35.0, 35.0)))


def fit_logistic(
    train_x: np.ndarray, train_y: np.ndarray, val_x: np.ndarray, val_y: np.ndarray
) -> dict[str, Any]:
    if len(np.unique(train_y)) != 2 or len(np.unique(val_y)) != 2:
        raise ValueError("both classes required in train and validation")
    mean = train_x.mean(axis=0)
    scale = np.maximum(train_x.std(axis=0), 1.0)
    design = _design(train_x, mean, scale)
    weights = np.zeros(design.shape[1])
    weights[0] = float(np.log(np.mean(train_y) / (1 - np.mean(train_y))))
    for _ in range(2000):
        gradient = design.T @ (_sigmoid(design @ weights) - train_y) / len(train_y)
        gradient[1:] += 0.01 * weights[1:]
        weights -= 0.2 * gradient
    validation_logits = _design(val_x, mean, scale) @ weights
    calibration = np.asarray([1.0, 0.0])
    for _ in range(2000):
        difference = _sigmoid(calibration[0] * validation_logits + calibration[1]) - val_y
        gradient = np.asarray([np.mean(difference * validation_logits), np.mean(difference)])
        gradient[0] += 0.01 * (calibration[0] - 1.0)
        calibration -= 0.05 * gradient
    return {
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "weights": weights.tolist(),
        "calibration": calibration.tolist(),
        "method": "logistic_l2_validation_sigmoid",
    }


def predict_logistic(model: dict[str, Any], x: np.ndarray) -> np.ndarray:
    logits = _design(x, np.asarray(model["mean"]), np.asarray(model["scale"])) @ np.asarray(model["weights"])
    slope, intercept = model["calibration"]
    return _sigmoid(slope * logits + intercept)


def fit_quantile(x: np.ndarray, y: np.ndarray, quantile: float = 0.9) -> dict[str, Any]:
    mean = x.mean(axis=0)
    scale = np.maximum(x.std(axis=0), 1.0)
    design = _design(x, mean, scale)
    weights = np.zeros(design.shape[1])
    weights[0] = float(np.quantile(y, quantile))
    for step in range(4000):
        error = y - design @ weights
        gradient = design.T @ np.where(error > 0, -quantile, 1 - quantile) / len(y)
        gradient[1:] += 0.001 * weights[1:]
        weights -= (0.04 if step < 2000 else 0.015) * gradient
    return {
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "weights": weights.tolist(),
        "quantile": quantile,
        "method": "linear_pinball_subgradient",
    }


def predict_quantile(model: dict[str, Any], x: np.ndarray) -> np.ndarray:
    prediction = _design(x, np.asarray(model["mean"]), np.asarray(model["scale"])) @ np.asarray(
        model["weights"]
    )
    return np.maximum(0.0, prediction)


def train(output: Path) -> dict[str, Any]:
    episodes, actions, dataset_manifest = load_frames(output)
    model_path = output / "models.json"
    manifest_path = output / "model_manifest.json"
    if model_path.exists() or manifest_path.exists():
        if not model_path.exists() or not manifest_path.exists():
            raise RuntimeError("partial model artifact")
        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        if saved["model_sha256"] != sha256(model_path) or saved["dataset_files"] != dataset_manifest["files"]:
            raise RuntimeError("model artifact or dataset changed")
        if saved["trainer_sha256"] != sha256(Path(__file__)):
            raise RuntimeError("training implementation changed")
        return saved
    train_ep = episodes[episodes["split"] == "train"]
    val_ep = episodes[episodes["split"] == "validation"]
    joined = joined_actions(episodes, actions)
    train_act = joined[joined["split"] == "train"]
    val_act = joined[joined["split"] == "validation"]
    breach = fit_logistic(
        episode_matrix(train_ep),
        train_ep["breach_within_horizon"].to_numpy(dtype=int),
        episode_matrix(val_ep),
        val_ep["breach_within_horizon"].to_numpy(dtype=int),
    )
    hazard_train_x, hazard_train_y = hazard_matrix(train_ep, training=True)
    hazard_val_x, hazard_val_y = hazard_matrix(val_ep, training=True)
    assert hazard_train_y is not None and hazard_val_y is not None
    hazard = fit_logistic(hazard_train_x, hazard_train_y, hazard_val_x, hazard_val_y)
    active_train = train_act[train_act["action_kind"] != "noop"]
    ttr = fit_quantile(action_matrix(active_train), active_train["ttr_s"].to_numpy(dtype=float))
    post = fit_logistic(
        action_matrix(train_act),
        train_act["post_sla"].to_numpy(dtype=int),
        action_matrix(val_act),
        val_act["post_sla"].to_numpy(dtype=int),
    )
    bounds = {name: [float(train_ep[name].min()), float(train_ep[name].max())] for name in FEATURES}
    models = {"breach": breach, "hazard": hazard, "ttr": ttr, "post": post, "bounds": bounds}
    model_path.write_text(json.dumps(models, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "protocol_version": "phase2-model-v1",
        "data_source": "SIMULATION_ONLY",
        "dataset_files": dataset_manifest["files"],
        "split_sha256": dataset_manifest["split_sha256"],
        "model_sha256": sha256(model_path),
        "trainer_sha256": sha256(Path(__file__)),
        "estimator": "numpy_logistic_and_linear_quantile",
        "features": list(FEATURES),
        "train_rows": {"episodes": len(train_ep), "actions": len(train_act)},
        "validation_rows": {"episodes": len(val_ep), "actions": len(val_act)},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def load_models(output: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads((output / "model_manifest.json").read_text(encoding="utf-8"))
    if manifest["trainer_sha256"] != sha256(Path(__file__)):
        raise RuntimeError("training implementation changed")
    if sha256(output / "models.json") != manifest["model_sha256"]:
        raise RuntimeError("model checksum mismatch")
    dataset_manifest = json.loads((output / "dataset_manifest.json").read_text(encoding="utf-8"))
    if manifest["dataset_files"] != dataset_manifest["files"]:
        raise RuntimeError("model/dataset lineage mismatch")
    if dataset_manifest["split_sha256"] != sha256(SPLIT_PATH):
        raise RuntimeError("frozen split changed")
    for name, digest in dataset_manifest["files"].items():
        if sha256(output / name) != digest:
            raise RuntimeError(f"dataset checksum mismatch: {name}")
    return json.loads((output / "models.json").read_text(encoding="utf-8")), manifest


def cumulative_incidence(model: dict[str, Any], episode_x: np.ndarray) -> np.ndarray:
    rows = np.asarray([[*features, float(tick)] for features in episode_x for tick in range(1, HORIZON + 1)])
    hazard = predict_logistic(model, rows).reshape(len(episode_x), HORIZON)
    return 1 - np.cumprod(1 - hazard, axis=1)


def quantile_time(cdf: np.ndarray, quantile: float) -> np.ndarray:
    crossed = cdf >= quantile
    return np.where(crossed.any(axis=1), crossed.argmax(axis=1) + 1, np.nan)


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    indices = np.minimum((p * bins).astype(int), bins - 1)
    return float(
        sum(
            np.mean(indices == i) * abs(np.mean(y[indices == i]) - np.mean(p[indices == i]))
            for i in range(bins)
            if np.any(indices == i)
        )
    )


def auc_roc(y: np.ndarray, p: np.ndarray) -> float | None:
    positive = int(np.sum(y))
    negative = len(y) - positive
    if not positive or not negative:
        return None
    ranks = pd.Series(p).rank(method="average").to_numpy(dtype=float)
    return float((np.sum(ranks[y == 1]) - positive * (positive + 1) / 2) / (positive * negative))


def average_precision(y: np.ndarray, p: np.ndarray) -> float | None:
    positives = int(np.sum(y))
    if not positives or positives == len(y):
        return None
    order = np.argsort(-p, kind="stable")
    sorted_y, sorted_p = y[order], p[order]
    score = 0.0
    true_positives = 0
    total = 0
    index = 0
    while index < len(y):
        end = index + 1
        while end < len(y) and sorted_p[end] == sorted_p[index]:
            end += 1
        group_positive = int(np.sum(sorted_y[index:end]))
        true_positives += group_positive
        total += end - index
        score += (group_positive / positives) * (true_positives / total)
        index = end
    return float(score)


def binary_metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float | None]:
    return {
        "n": float(len(y)),
        "prevalence": float(np.mean(y)),
        "brier": float(np.mean((y - p) ** 2)),
        "pr_auc": average_precision(y, p),
        "auroc": auc_roc(y, p),
        "ece_10_bins": ece(y, p),
    }


class TrainedForecastProvider:
    """Opt-in checked JSON predictor; no external calls or pickle loading."""

    def __init__(self, output: Path):
        self.models, self.manifest = load_models(output)
        self.dataset_sha256 = hashlib.sha256(
            json.dumps(self.manifest["dataset_files"], sort_keys=True).encode()
        ).hexdigest()

    def _features(self, service: ServiceBundle, snapshot: TelemetrySnapshot) -> np.ndarray:
        node = next(n for n in snapshot.nodes if n.id == snapshot.active_node)
        slo = service.intent.latency_p95_ms
        return np.asarray(
            [
                snapshot.queue_depth,
                snapshot.arrival_rps,
                snapshot.cycle_ms,
                node.network_ms,
                slo,
                slo - snapshot.observed_p95_ms,
            ],
            dtype=float,
        )

    def predict(
        self, service: ServiceBundle, snapshot: TelemetrySnapshot, candidates: tuple[CandidateAction, ...]
    ) -> ForecastBundle:
        features = self._features(service, snapshot)
        bounds = self.models["bounds"]
        ood = any(
            value < lower - 0.1 * (upper - lower) or value > upper + 0.1 * (upper - lower)
            for value, (lower, upper) in zip(features, (bounds[name] for name in FEATURES), strict=True)
        )
        episode_x = features.reshape(1, -1)
        breach = float(predict_logistic(self.models["breach"], episode_x)[0])
        cdf = cumulative_incidence(self.models["hazard"], episode_x)
        q10 = quantile_time(cdf, 0.1)[0]
        action_rows = []
        for candidate in candidates:
            node = next(n for n in snapshot.nodes if n.id == candidate.target_node)
            one_hot = [float(candidate.kind.value == kind) for kind in ("scale_out", "migrate", "noop")]
            action_rows.append([*features, *one_hot, float(candidate.target_replicas), node.network_ms])
        action_x = np.asarray(action_rows, dtype=float)
        post = predict_logistic(self.models["post"], action_x)
        active_indices = [i for i, candidate in enumerate(candidates) if candidate.kind.value != "noop"]
        ttr_values: np.ndarray | list[float] = (
            predict_quantile(self.models["ttr"], action_x[active_indices]) if active_indices else []
        )
        ttr = {candidate.id: 0.0 for candidate in candidates}
        for index, value in zip(active_indices, ttr_values, strict=True):
            ttr[candidates[index].id] = float(value)
        return ForecastBundle(
            snapshot_id=snapshot.id,
            service_id=service.id,
            valid_until=snapshot.observed_at + timedelta(seconds=30),
            model_version=self.manifest["model_sha256"][:12],
            dataset_sha256=self.dataset_sha256,
            breach_probability_12s=breach,
            ttv_q10_s=None if np.isnan(q10) else float(q10),
            ttr_q90_s=ttr,
            post_sla_probability={
                candidate.id: float(value) for candidate, value in zip(candidates, post, strict=True)
            },
            ood=ood,
        )


def decision_metrics(output: Path, test_ep: pd.DataFrame, test_actions: pd.DataFrame) -> dict[str, Any]:
    from .decision import decide, propose

    provider = TrainedForecastProvider(output)
    outcomes = {
        (record.episode_id, record.action_kind): int(record.post_sla)
        for record in test_actions.itertuples(index=False)
    }
    selected: dict[str, int] = {"scale_out": 0, "migrate": 0, "noop": 0}
    success = 0
    no_op_success = 0
    ood_count = 0
    for record in test_ep.itertuples(index=False):
        intent = TypedIntent(
            service_name=f"service-{record.seed}",
            tier="Gold",
            latency_p95_ms=record.slo_ms,
            minimum_model_quality=0.9,
            max_replicas=2,
            allowed_regions=("eu-gr", "eu-de"),
            allowed_actions=(ActionKind.SCALE_OUT, ActionKind.MIGRATE),
        )
        service = ServiceBundle(tenant_id="research", intent=intent)
        snapshot = TelemetrySnapshot(
            seed=record.seed,
            queue_depth=record.queue_depth,
            arrival_rps=record.arrival_rps,
            cycle_ms=record.cycle_ms,
            observed_p95_ms=record.observed_p95_ms,
            nodes=(
                TopologyNode(id="edge-a", region="eu-gr", network_ms=record.network_ms, replica_capacity=4),
                TopologyNode(id="cloud-a", region="eu-de", network_ms=80, replica_capacity=2),
            ),
        )
        candidates = propose(service, snapshot)
        forecast = provider.predict(service, snapshot, candidates)
        decision = decide(service, snapshot, candidates, forecast=forecast)
        chosen = next(candidate for candidate in candidates if candidate.id == decision.selected_candidate_id)
        selected[chosen.kind.value] += 1
        success += outcomes[(record.episode_id, chosen.kind.value)]
        no_op_success += outcomes[(record.episode_id, "noop")]
        ood_count += int(forecast.ood)
    count = len(test_ep)
    return {
        "n": count,
        "selected_actions": selected,
        "ood_snapshots": ood_count,
        "simulated_slo_rate_selected": success / count,
        "simulated_slo_rate_noop": no_op_success / count,
        "note": "Counterfactual outcomes share the same seeded synthetic episode; not hardware evidence.",
    }


def evaluate(output: Path) -> dict[str, Any]:
    episodes, actions, _ = load_frames(output)
    models, model_manifest = load_models(output)
    metrics_path = output / "metrics.json"
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        if metrics["model_sha256"] != model_manifest["model_sha256"]:
            raise RuntimeError("evaluation/model mismatch")
        if metrics["evaluator_sha256"] != sha256(Path(__file__)):
            raise RuntimeError("evaluation implementation changed")
        return metrics
    train_ep = episodes[episodes["split"] == "train"]
    test_ep = episodes[episodes["split"] == "test"]
    test_act = joined_actions(episodes, actions)
    test_act = test_act[test_act["split"] == "test"]
    breach_y = test_ep["breach_within_horizon"].to_numpy(dtype=int)
    breach_x = episode_matrix(test_ep)
    breach_p = predict_logistic(models["breach"], breach_x)
    prior = float(train_ep["breach_within_horizon"].mean())
    threshold = (test_ep["headroom_ms"].to_numpy(dtype=float) < 70.0).astype(float)
    cdf = cumulative_incidence(models["hazard"], breach_x)
    event_times = test_ep["ttv_observed_s"].to_numpy(dtype=float)
    observed = ~np.isnan(event_times)
    truth = np.asarray([observed & (event_times <= tick) for tick in range(1, HORIZON + 1)]).T
    q10 = quantile_time(cdf, 0.1)
    q50 = quantile_time(cdf, 0.5)
    q10_observed = np.nan_to_num(q10[observed], nan=HORIZON + 1)
    q50_observed = np.nan_to_num(q50[observed], nan=HORIZON + 1)
    active = test_act[test_act["action_kind"] != "noop"]
    ttr_y = active["ttr_s"].to_numpy(dtype=float)
    ttr_q90 = predict_quantile(models["ttr"], action_matrix(active))
    post_y = test_act["post_sla"].to_numpy(dtype=int)
    post_p = predict_logistic(models["post"], action_matrix(test_act))
    metrics = {
        "protocol_version": "phase2-evaluation-v1",
        "data_source": "SIMULATION_ONLY",
        "model_sha256": model_manifest["model_sha256"],
        "evaluator_sha256": sha256(Path(__file__)),
        "test_seed_range": [80, 99],
        "breach": {
            "constant_prior": binary_metrics(breach_y, np.full(len(breach_y), prior)),
            "headroom_threshold_70ms": binary_metrics(breach_y, threshold),
            "calibrated_logistic": binary_metrics(breach_y, breach_p),
        },
        "ttv": {
            "n": len(test_ep),
            "observed_events": int(np.sum(observed)),
            "right_censored": int(np.sum(~observed)),
            "integrated_brier_1_to_12s": float(np.mean((cdf - truth) ** 2)),
            "q10_pinball_observed_only": float(
                np.mean(
                    np.where(
                        event_times[observed] >= q10_observed,
                        0.1 * (event_times[observed] - q10_observed),
                        0.9 * (q10_observed - event_times[observed]),
                    )
                )
            ),
            "q50_mae_observed_only": float(np.mean(np.abs(event_times[observed] - q50_observed))),
        },
        "ttr": {
            "n": len(active),
            "q90_pinball": float(
                np.mean(np.where(ttr_y >= ttr_q90, 0.9 * (ttr_y - ttr_q90), 0.1 * (ttr_q90 - ttr_y)))
            ),
            "q90_upper_coverage": float(np.mean(ttr_y <= ttr_q90)),
        },
        "post_sla": binary_metrics(post_y, post_p),
        "decision": decision_metrics(output, test_ep, test_act),
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metrics
