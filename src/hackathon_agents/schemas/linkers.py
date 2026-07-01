from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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

