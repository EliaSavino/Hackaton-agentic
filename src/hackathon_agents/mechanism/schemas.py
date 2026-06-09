from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hackathon_agents.mechanism.mechanism_classes import MechanismClass


class LiteraturePrior(BaseModel):
    """Local or API-derived literature context used as a prior, not as proof."""

    query: str
    summary: str
    key_findings: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source: Literal["mock", "local", "api", "dry-run"] = "mock"

    model_config = ConfigDict(extra="forbid")


class MechanismHypothesis(BaseModel):
    """Structured hypothesis for a plausible reaction mechanism.

    All claims in this object are hypotheses until supported by kinetic data,
    literature evidence, or calculations recorded elsewhere in state.
    """

    id: str
    title: str
    mechanism_class: MechanismClass
    species: list[str]
    elementary_steps: list[str]
    rate_law_form: str
    assumptions: list[str] = Field(default_factory=list)
    required_observables: list[str] = Field(default_factory=list)
    predicted_signatures: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.25, ge=0.0, le=1.0)
    uncertainty: float = Field(default=0.75, ge=0.0, le=1.0)
    literature_support: list[str] = Field(default_factory=list)
    dft_requirements: list[str] = Field(default_factory=list)
    falsifying_experiments: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class KineticExperimentVariables(BaseModel):
    """Controllable variables for a robot-submitted kinetic experiment."""

    concentrations: dict[str, float] = Field(default_factory=dict)
    temperature: float = Field(default=298.15, gt=0.0)
    residence_time: float = Field(default=10.0, gt=0.0)
    flow_rate_profile: list[float] = Field(default_factory=list)
    light_intensity: float = Field(default=0.0, ge=0.0)
    catalyst_loading: float = Field(default=0.0, ge=0.0)
    solvent: str = "MeCN"
    additives: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class KineticExperiment(BaseModel):
    """A proposed kinetic experiment with robot-facing protocol metadata."""

    id: str
    objective: str
    variables: KineticExperimentVariables
    measured_species: list[str] = Field(default_factory=lambda: ["A", "B", "P"])
    sampling_strategy: str = "uniform time-resolved sampling"
    expected_information_gain: float = Field(default=0.0, ge=0.0)
    safety_constraints: list[str] = Field(default_factory=list)
    robot_protocol: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class KineticDataset(BaseModel):
    """Parsed time-resolved concentration data for one kinetic experiment."""

    experiment_id: str
    time_points: list[float]
    concentration_profiles: dict[str, list[float]]
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_files: list[str] = Field(default_factory=list)
    parsed_ok: bool = True
    quality_flags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_profile_lengths(self) -> "KineticDataset":
        """Require each concentration profile to align with the time grid."""

        if not self.time_points:
            raise ValueError("time_points must not be empty")
        for species, profile in self.concentration_profiles.items():
            if len(profile) != len(self.time_points):
                raise ValueError(
                    f"concentration profile for {species!r} has {len(profile)} values; "
                    f"expected {len(self.time_points)}"
                )
        if any(next_time < current_time for current_time, next_time in zip(self.time_points, self.time_points[1:])):
            raise ValueError("time_points must be sorted in ascending order")
        return self


class FitResult(BaseModel):
    """Least-squares result for one hypothesis against one kinetic dataset."""

    hypothesis_id: str
    experiment_id: str
    ok: bool
    model_name: str
    parameters: dict[str, float] = Field(default_factory=dict)
    parameter_uncertainty: dict[str, float] = Field(default_factory=dict)
    residual_norm: float | None = None
    rmse: float | None = None
    aic: float | None = None
    bic: float | None = None
    confidence_update: float = Field(default=0.0, ge=-1.0, le=1.0)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    model_config = ConfigDict(extra="forbid")


class MechanismRanking(BaseModel):
    """Current data-weighted ranking for a mechanism hypothesis."""

    hypothesis_id: str
    title: str
    mechanism_class: MechanismClass
    score: float = Field(ge=0.0, le=1.0)
    uncertainty: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class CriticAssessment(BaseModel):
    """Structured critic notes for one loop round."""

    round_index: int
    plausibility_notes: list[str] = Field(default_factory=list)
    overfitting_notes: list[str] = Field(default_factory=list)
    identifiability_notes: list[str] = Field(default_factory=list)
    missing_controls: list[str] = Field(default_factory=list)
    dft_notes: list[str] = Field(default_factory=list)
    robot_feasibility_notes: list[str] = Field(default_factory=list)
    requires_human_review: bool = False

    model_config = ConfigDict(extra="forbid")
