"""Four mandatory clauses compiled from a small structured intent."""
from dataclasses import dataclass
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False,
                              validate_default=True)


class Intent(StrictModel):
    tenant: str = Field(min_length=1)
    end_to_end_latency_ms: float = Field(gt=0)
    minimum_model_quality: float = Field(ge=0, le=1)
    service_availability: float = Field(gt=0, le=1)
    max_update_disruption_s: float = Field(ge=0)


@dataclass(frozen=True)
class ServiceState:
    latency_ms: float
    quality: float
    availability: float
    disruption_s: float


@dataclass(frozen=True)
class Contract:
    intent: Intent

    def violations(self, state: ServiceState) -> tuple[str, ...]:
        clauses = (
            ("END_TO_END_LATENCY", state.latency_ms > self.intent.end_to_end_latency_ms),
            ("MINIMUM_MODEL_QUALITY", state.quality < self.intent.minimum_model_quality),
            ("SERVICE_AVAILABILITY", state.availability < self.intent.service_availability),
            ("MAX_UPDATE_DISRUPTION", state.disruption_s > self.intent.max_update_disruption_s),
        )
        return tuple(name for name, breached in clauses if breached)


def compile_contract(intent: Intent) -> Contract:
    return Contract(intent)

