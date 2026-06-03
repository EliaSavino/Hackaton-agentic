from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from hackathon_agents.config import RunMode
from hackathon_agents.schemas.molecules import MoleculeRecord
from hackathon_agents.schemas.results import ToolExecutionRecord, ToolResult
from hackathon_agents.schemas.tasks import CriticDecision, DiscoveryPlan


class DiscoveryStatePayload(BaseModel):
    original_user_request: str
    plan: DiscoveryPlan | None = None
    candidate_molecules: list[MoleculeRecord] = Field(default_factory=list)
    tool_results: list[ToolExecutionRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    critic_notes: list[str] = Field(default_factory=list)
    critic_decisions: list[CriticDecision] = Field(default_factory=list)
    final_report_path: str | None = None
    messages: list[str] = Field(default_factory=list)
    run_dir: str | None = None
    run_mode: RunMode = RunMode.CHEAP
    iteration: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=3, ge=1)
    needs_more_passes: bool = False
    stop_reason: str | None = None
    requested_next_actions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def append_message(self, message: str) -> None:
        self.messages.append(message)

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.messages.append(f"error: {message}")

    def add_tool_result(self, tool_name: str, result: ToolResult) -> None:
        self.tool_results.append(ToolExecutionRecord(tool_name=tool_name, result=result))
        if not result.ok and result.error:
            self.add_error(f"{tool_name}: {result.error}")

    @property
    def run_path(self) -> Path | None:
        return Path(self.run_dir) if self.run_dir else None
