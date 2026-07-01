from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Objective dimensions the autonomous critic is allowed to reweight. Kept as a
# module constant so the critic, the objective builder, and tests agree.
ADC_GOAL_KEYS = (
    "solubility",
    "size",
    "flexibility",
    "synthesizability",
    "cleavability",
    "stability",
    "similarity",
)


class ADCGoalProfile(BaseModel):
    """Compact, bounded description of an ADC-linker design objective.

    This is the action space the autonomous critic edits between passes: seven
    weights plus two constraint toggles and a few target windows. A deterministic
    builder (``tools/adc_linker_objective.build_adc_linkinvent_objective``) turns
    a profile into a guaranteed-valid REINVENT LinkInvent scoring function, so
    the LLM never emits raw REINVENT config.
    """

    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "solubility": 1.0,
            "size": 0.6,
            "flexibility": 0.4,
            "synthesizability": 0.8,
            "cleavability": 1.0,
            "stability": 0.7,
            # Off by default: the reference corpus has no linker SMILES yet.
            "similarity": 0.0,
        }
    )
    require_cleavable_motif: bool = True
    enforce_stability_alerts: bool = True
    target_logp: float = 2.0
    mw_low: float = 150.0
    mw_high: float = 600.0
    max_rot_bonds: int = 10
    max_sa_score: float = 5.0

    model_config = ConfigDict(extra="forbid")

    @field_validator("weights")
    @classmethod
    def _clamp_weights(cls, value: dict[str, float]) -> dict[str, float]:
        # Ignore unknown keys and clamp each weight to [0, 1]; missing keys → 0.0.
        cleaned = {key: 0.0 for key in ADC_GOAL_KEYS}
        for key, weight in value.items():
            if key in cleaned:
                try:
                    cleaned[key] = max(0.0, min(1.0, float(weight)))
                except (TypeError, ValueError):
                    cleaned[key] = 0.0
        return cleaned


class ReferenceLinkerClass(BaseModel):
    name: str
    linker_class: str
    triggers: list[str] = Field(default_factory=list)
    conjugation_handles: list[str] = Field(default_factory=list)
    payload_handles: list[str] = Field(default_factory=list)
    release_logic: str
    strengths: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    example_adcs: list[str] = Field(default_factory=list)


class LinkerProofPoint(BaseModel):
    name: str
    score: float = Field(ge=0.0, le=1.0)
    value: str | float | int | bool | None = None
    rationale: str
    evidence: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class LinkerScorecard(BaseModel):
    plasma_stability: float = Field(ge=0.0, le=1.0)
    tumor_release: float = Field(ge=0.0, le=1.0)
    aqueous_solubility: float = Field(ge=0.0, le=1.0)
    low_aggregation_risk: float = Field(ge=0.0, le=1.0)
    payload_compatibility: float = Field(ge=0.0, le=1.0)
    manufacturability: float = Field(ge=0.0, le=1.0)
    novelty: float = Field(ge=0.0, le=1.0)
    overall: float = Field(ge=0.0, le=1.0)


class LinkerCandidate(BaseModel):
    candidate_id: str
    name: str
    description: str
    model_fragment_smiles: str
    conjugation_handle: str
    payload_handle: str
    cleavage_triggers: list[str] = Field(default_factory=list)
    spacer_modules: list[str] = Field(default_factory=list)
    solubilizing_groups: list[str] = Field(default_factory=list)
    self_immolative_group: str | None = None
    compatible_payload_classes: list[str] = Field(default_factory=list)
    likely_release_mechanism: str
    predicted_release_products: list[str] = Field(default_factory=list)
    synthesis_steps: list[str] = Field(default_factory=list)
    novelty_claim: str
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    reference_control: bool = False
    descriptors: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    proof_points: list[LinkerProofPoint] = Field(default_factory=list)
    scorecard: LinkerScorecard | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LinkerDesignRequest(BaseModel):
    objective: str = "Design a next-generation ADC linker with improved stability, tunable release, and broad payload compatibility."
    payload_classes: list[str] = Field(
        default_factory=lambda: ["cytotoxin", "oligonucleotide", "immunomodulator"]
    )
    desired_triggers: list[str] = Field(
        default_factory=lambda: ["lysosomal protease", "acidic pH", "reducing environment", "tumor enzyme"]
    )
    conjugation_handles: list[str] = Field(default_factory=lambda: ["maleimide", "strain-promoted azide"])
    max_candidates: int = Field(default=8, ge=1, le=50)
    include_reference_controls: bool = True
    reference_corpus_path: str | None = None
    output_dir: str | None = None

