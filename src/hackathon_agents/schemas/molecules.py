from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MoleculeRecord(BaseModel):
    smiles: str
    name: str | None = None
    source: str = "generated"
    descriptors: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
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
