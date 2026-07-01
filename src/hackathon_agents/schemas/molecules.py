from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MoleculeRecord(BaseModel):
    smiles: str
    name: str | None = None
    source: str = "generated"
    # Free-form: RDKit descriptors include nested values (element_counts dict,
    # elements list, reactive_alert_hits dict) alongside scalar descriptors, and
    # tools/agents may attach ADC subscores. Kept permissive so the LangGraph
    # state round-trip (model_dump -> model_validate) never rejects them.
    descriptors: dict[str, Any] = Field(default_factory=dict)
    score: float | None = None
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MoleculeFilterConstraints(BaseModel):
    min_mol_wt: float | None = None
    max_mol_wt: float | None = 650.0
    min_qed: float | None = None
    max_logp: float | None = 6.0
    max_tpsa: float | None = None
    allowed_elements: set[str] | None = None
