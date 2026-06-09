from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from hackathon_agents.mechanism.schemas import (
    CriticAssessment,
    FitResult,
    KineticDataset,
    KineticExperiment,
    LiteraturePrior,
    MechanismHypothesis,
    MechanismRanking,
)
from hackathon_agents.tools.dft_job import DFTJob, DFTResult


MechanismRunMode = Literal["mock", "dry-run", "real"]


class MechanismDiscoveryState(BaseModel):
    """Typed state for the bounded mechanism discovery loop."""

    objective: str
    mode: MechanismRunMode = "mock"
    run_dir: str | None = None
    round_index: int = Field(default=0, ge=0)
    max_rounds: int = Field(default=1, ge=1)
    literature_prior: LiteraturePrior | None = None
    hypotheses: list[MechanismHypothesis] = Field(default_factory=list)
    experiments: list[KineticExperiment] = Field(default_factory=list)
    datasets: list[KineticDataset] = Field(default_factory=list)
    fit_results: list[FitResult] = Field(default_factory=list)
    rankings: list[MechanismRanking] = Field(default_factory=list)
    dft_jobs: list[DFTJob] = Field(default_factory=list)
    dft_results: list[DFTResult] = Field(default_factory=list)
    robot_jobs: list[str] = Field(default_factory=list)
    hpc_jobs: list[str] = Field(default_factory=list)
    critic_assessments: list[CriticAssessment] = Field(default_factory=list)
    critic_notes: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    report_json_path: str | None = None
    report_docx_path: str | None = None
    next_experiment: KineticExperiment | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def run_path(self) -> Path | None:
        """Return the run directory as a Path when it has been assigned."""

        return Path(self.run_dir) if self.run_dir else None

    def add_error(self, message: str) -> None:
        """Record a recoverable error without stopping the bounded loop."""

        self.errors.append(message)

    def add_validation_error(self, message: str) -> None:
        """Record schema validation failures for agent outputs."""

        self.validation_errors.append(message)
        self.add_error(message)

    def save_json(self, path: str | Path | None = None) -> Path:
        """Persist the full state as JSON for auditability."""

        if path is None:
            if self.run_path is None:
                raise ValueError("run_dir is required when no explicit path is provided")
            path = self.run_path / "state.json"
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return output
