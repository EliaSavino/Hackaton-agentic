from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DFTCalculationType(str, Enum):
    """Supported DFT calculation request types."""

    OPTIMIZATION = "optimization"
    FREQUENCY = "frequency"
    SINGLE_POINT = "single_point"
    TRANSITION_STATE = "transition_state"


class DFTJob(BaseModel):
    """Schema for a DFT calculation request sent to an HPC backend."""

    id: str
    molecule_or_structure: str
    charge: int = 0
    multiplicity: int = Field(default=1, ge=1)
    method: str = "B3LYP"
    basis: str = "def2-SVP"
    solvent_model: str | None = None
    calculation_type: DFTCalculationType = DFTCalculationType.OPTIMIZATION
    reason_for_calculation: str
    linked_hypothesis_id: str

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class DFTResult(BaseModel):
    """Parsed result stub for a completed or dry-run DFT job."""

    job_id: str
    status: str
    energy_hartree: float | None = None
    frequencies_cm1: list[float] = Field(default_factory=list)
    output_files: list[str] = Field(default_factory=list)
    parsed_ok: bool = True
    summary: str = ""

    model_config = ConfigDict(extra="forbid")
