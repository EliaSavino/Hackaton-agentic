from __future__ import annotations

from pydantic import BaseModel, Field


class DiscoveryPlanStep(BaseModel):
    name: str
    description: str
    agent: str
    tool_names: list[str] = Field(default_factory=list)


class DiscoveryPlan(BaseModel):
    objective: str
    assumptions: list[str] = Field(default_factory=list)
    steps: list[DiscoveryPlanStep] = Field(default_factory=list)


class CriticDecision(BaseModel):
    needs_more_passes: bool
    reason: str
    requested_next_actions: list[str] = Field(default_factory=list)
    stop_reason: str | None = None
    valid_candidate_count: int = 0
    best_score: float | None = None
