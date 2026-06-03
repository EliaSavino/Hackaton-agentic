from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


PaperSourceType = Literal["text", "markdown", "pdf", "docx", "unknown"]
FindingSeverity = Literal["info", "low", "medium", "high"]
ChecklistStatus = Literal["present", "partial", "missing", "not_applicable"]
ReviewRecommendation = Literal["ready_for_triage", "needs_manual_review", "high_risk"]


class EvidenceSpan(BaseModel):
    text: str
    section: str | None = None
    source_path: str | None = None
    char_start: int | None = None
    char_end: int | None = None


class PaperMetadata(BaseModel):
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    source_path: str | None = None
    source_type: PaperSourceType = "unknown"


class PaperSection(BaseModel):
    name: str
    text: str
    word_count: int


class PaperClaim(BaseModel):
    claim: str
    claim_type: Literal["objective", "method", "result", "conclusion", "limitation", "unknown"] = "unknown"
    evidence: EvidenceSpan | None = None
    confidence: Literal["low", "medium", "high"] = "medium"


class ReviewFinding(BaseModel):
    category: str
    severity: FindingSeverity
    finding: str
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ReproducibilityChecklistItem(BaseModel):
    item: str
    status: ChecklistStatus
    rationale: str
    evidence: EvidenceSpan | None = None


class PaperReview(BaseModel):
    metadata: PaperMetadata
    abstract: str | None = None
    sections: list[PaperSection] = Field(default_factory=list)
    claims: list[PaperClaim] = Field(default_factory=list)
    strengths: list[ReviewFinding] = Field(default_factory=list)
    limitations: list[ReviewFinding] = Field(default_factory=list)
    reproducibility_checklist: list[ReproducibilityChecklistItem] = Field(default_factory=list)
    focus_question_notes: list[ReviewFinding] = Field(default_factory=list)
    recommendation: ReviewRecommendation = "needs_manual_review"
    summary: str
