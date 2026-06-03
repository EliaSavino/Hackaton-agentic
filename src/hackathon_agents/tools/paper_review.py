from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from hackathon_agents.schemas.papers import (
    EvidenceSpan,
    PaperClaim,
    PaperMetadata,
    PaperReview,
    PaperSection,
    ReproducibilityChecklistItem,
    ReviewFinding,
)
from hackathon_agents.tools.base import error_result, ok_result


KNOWN_SECTION_HEADERS = [
    "abstract",
    "introduction",
    "background",
    "related work",
    "methods",
    "materials and methods",
    "experimental",
    "experiments",
    "results",
    "discussion",
    "conclusion",
    "conclusions",
    "limitations",
    "data availability",
    "code availability",
    "supporting information",
    "references",
]

CLAIM_PATTERNS = [
    r"\bwe (?:show|demonstrate|report|find|found|identify|propose|developed|designed)\b",
    r"\bresults? (?:show|suggest|indicate|demonstrate)\b",
    r"\bthis (?:study|work|paper) (?:shows|demonstrates|reports|presents|introduces)\b",
    r"\b(?:increased|decreased|improved|reduced|achieved|outperformed)\b",
]

OVERCLAIM_TERMS = [
    "breakthrough",
    "definitive",
    "guaranteed",
    "cure",
    "first ever",
    "unprecedented",
    "solves",
]


class PaperTextInput(BaseModel):
    path: str | None = None
    text: str | None = None
    max_chars: int = Field(default=250_000, ge=1, le=2_000_000)

    @model_validator(mode="after")
    def require_path_or_text(self) -> "PaperTextInput":
        if not self.path and not self.text:
            raise ValueError("Either path or text is required.")
        return self


class PaperReviewInput(PaperTextInput):
    focus_questions: list[str] = Field(default_factory=list)
    domain: Literal["general", "chemistry", "biology", "chem_bio"] = "chem_bio"
    review_depth: Literal["quick", "standard", "deep"] = "standard"
    output_path: str | None = None


def load_paper_text(input_data: PaperTextInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, PaperTextInput) else PaperTextInput.model_validate(input_data)
    try:
        if parsed.text is not None:
            text = _normalize_text(parsed.text[: parsed.max_chars])
            return ok_result(
                {
                    "text": text,
                    "char_count": len(text),
                    "source_path": None,
                    "source_type": "text",
                }
            )

        assert parsed.path is not None
        path = Path(parsed.path)
        if not path.exists():
            return error_result("Paper path does not exist.", {"path": str(path)})
        if not path.is_file():
            return error_result("Paper path is not a file.", {"path": str(path)})

        suffix = path.suffix.lower()
        if suffix == ".pdf":
            text = _read_pdf(path)
            source_type = "pdf"
        elif suffix == ".docx":
            text = _read_docx(path)
            source_type = "docx"
        elif suffix in {".md", ".markdown"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            source_type = "markdown"
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
            source_type = "text"

        text = _normalize_text(text[: parsed.max_chars])
        return ok_result(
            {
                "text": text,
                "char_count": len(text),
                "source_path": str(path),
                "source_type": source_type,
            }
        )
    except Exception as exc:
        return error_result(str(exc), {"path": parsed.path})


def split_paper_sections(input_data: PaperTextInput | dict[str, Any]):
    loaded = load_paper_text(input_data)
    if not loaded.ok:
        return loaded
    sections = _split_sections(loaded.data["text"])
    return ok_result(
        {
            "sections": [section.model_dump(mode="json") for section in sections],
            "section_count": len(sections),
        }
    )


def review_paper(input_data: PaperReviewInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, PaperReviewInput) else PaperReviewInput.model_validate(input_data)
    loaded = load_paper_text(parsed)
    if not loaded.ok:
        return loaded

    text = loaded.data["text"]
    source_path = loaded.data.get("source_path")
    source_type = loaded.data.get("source_type", "unknown")
    sections = _split_sections(text)
    section_map = {section.name.lower(): section for section in sections}
    metadata = _extract_metadata(text, source_path, source_type)
    abstract = _extract_abstract(section_map, text)
    claims = _extract_claims(sections, source_path, parsed.review_depth)
    checklist = _build_reproducibility_checklist(text, sections, parsed.domain, source_path)
    strengths = _build_strengths(checklist, sections, source_path)
    limitations = _build_limitations(text, sections, checklist, claims, parsed.domain, source_path)
    focus_notes = _answer_focus_questions(parsed.focus_questions, text, sections, source_path)
    recommendation = _recommend(limitations, checklist, claims)
    summary = _make_summary(metadata, claims, strengths, limitations, recommendation)

    review = PaperReview(
        metadata=metadata,
        abstract=abstract,
        sections=sections,
        claims=claims,
        strengths=strengths,
        limitations=limitations,
        reproducibility_checklist=checklist,
        focus_question_notes=focus_notes,
        recommendation=recommendation,
        summary=summary,
    )

    artifacts: list[str] = []
    if parsed.output_path:
        output = Path(parsed.output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(review.model_dump(mode="json"), indent=2), encoding="utf-8")
        artifacts.append(str(output))

    return ok_result(
        {
            "review": review.model_dump(mode="json"),
            "source": {
                "path": source_path,
                "type": source_type,
                "char_count": loaded.data.get("char_count"),
            },
        },
        artifacts,
    )


def batch_review_papers(paths: list[str], output_dir: str | None = None, domain: str = "chem_bio"):
    reviews: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    artifacts: list[str] = []
    for path in paths:
        output_path = None
        if output_dir:
            output_path = str(Path(output_dir) / f"{Path(path).stem}_review.json")
        result = review_paper({"path": path, "domain": domain, "output_path": output_path})
        if result.ok:
            reviews.append(result.data["review"])
            artifacts.extend(result.artifacts)
        else:
            errors.append({"path": path, "error": result.error or "review failed"})

    return ok_result({"reviews": reviews, "errors": errors, "review_count": len(reviews)}, artifacts)


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise RuntimeError("pypdf is required to read PDF papers.") from exc

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _read_docx(path: Path) -> str:
    try:
        from docx import Document
    except Exception as exc:
        raise RuntimeError("python-docx is required to read DOCX papers.") from exc

    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_sections(text: str) -> list[PaperSection]:
    lines = text.splitlines()
    section_starts: list[tuple[int, str]] = []
    known = {header.lower() for header in KNOWN_SECTION_HEADERS}

    for index, line in enumerate(lines):
        stripped = line.strip().strip(":")
        normalized = re.sub(r"^\d+(?:\.\d+)*\s+", "", stripped).lower()
        if normalized in known:
            section_starts.append((index, stripped.title()))

    if not section_starts:
        return [PaperSection(name="Full Text", text=text, word_count=_word_count(text))]

    sections: list[PaperSection] = []
    for offset, (line_index, name) in enumerate(section_starts):
        start = line_index + 1
        end = section_starts[offset + 1][0] if offset + 1 < len(section_starts) else len(lines)
        section_text = "\n".join(lines[start:end]).strip()
        if section_text:
            sections.append(PaperSection(name=name, text=section_text, word_count=_word_count(section_text)))

    return sections or [PaperSection(name="Full Text", text=text, word_count=_word_count(text))]


def _extract_metadata(text: str, source_path: str | None, source_type: str) -> PaperMetadata:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = None
    for line in lines[:12]:
        normalized = line.lower().strip(":")
        if normalized not in KNOWN_SECTION_HEADERS and len(line.split()) >= 3:
            title = line[:300]
            break

    doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", text, re.IGNORECASE)
    year_match = re.search(r"\b(19|20)\d{2}\b", text)

    authors: list[str] = []
    if title and title in lines:
        title_index = lines.index(title)
        if title_index + 1 < len(lines):
            candidate = lines[title_index + 1]
            if len(candidate) < 300 and re.search(r",| and |;", candidate, re.IGNORECASE):
                authors = [item.strip() for item in re.split(r",|;| and ", candidate) if item.strip()]

    return PaperMetadata(
        title=title,
        authors=authors[:20],
        year=int(year_match.group(0)) if year_match else None,
        doi=doi_match.group(0) if doi_match else None,
        source_path=source_path,
        source_type=source_type,  # type: ignore[arg-type]
    )


def _extract_abstract(section_map: dict[str, PaperSection], text: str) -> str | None:
    abstract_section = section_map.get("abstract")
    if abstract_section:
        return abstract_section.text[:2500]
    match = re.search(r"abstract\s*:?\s*(.{200,2500}?)(?:\n\s*(?:introduction|background|methods)\b)", text, re.IGNORECASE | re.DOTALL)
    if match:
        return _normalize_text(match.group(1))
    return None


def _extract_claims(sections: list[PaperSection], source_path: str | None, depth: str) -> list[PaperClaim]:
    limit = {"quick": 6, "standard": 12, "deep": 24}[depth]
    claims: list[PaperClaim] = []
    for section in sections:
        for sentence in _sentences(section.text):
            lowered = sentence.lower()
            if any(re.search(pattern, lowered) for pattern in CLAIM_PATTERNS):
                claim_type = _classify_claim(section.name, sentence)
                claims.append(
                    PaperClaim(
                        claim=sentence,
                        claim_type=claim_type,
                        evidence=EvidenceSpan(text=sentence, section=section.name, source_path=source_path),
                        confidence="medium",
                    )
                )
            if len(claims) >= limit:
                return claims
    return claims


def _classify_claim(section_name: str, sentence: str) -> str:
    section = section_name.lower()
    lowered = sentence.lower()
    if "method" in section or "experimental" in section:
        return "method"
    if "result" in section or any(term in lowered for term in ["increased", "decreased", "improved", "achieved"]):
        return "result"
    if "limitation" in section:
        return "limitation"
    if "conclusion" in section or "discussion" in section:
        return "conclusion"
    if any(term in lowered for term in ["objective", "aim", "goal"]):
        return "objective"
    return "unknown"


def _build_reproducibility_checklist(
    text: str,
    sections: list[PaperSection],
    domain: str,
    source_path: str | None,
) -> list[ReproducibilityChecklistItem]:
    checks = [
        ("Experimental or computational method described", [r"\bmethods?\b", r"\bexperimental\b", r"\bprotocol\b"]),
        ("Controls or baselines described", [r"\bcontrols?\b", r"\bbaseline\b", r"\bnegative control\b", r"\bpositive control\b"]),
        ("Replicates or sample size described", [r"\breplicat", r"\bn\s*=", r"\bsample size\b", r"\btriplicate\b"]),
        ("Statistical analysis described", [r"\bp\s*[<=>]", r"\bconfidence interval\b", r"\bstatistical", r"\bstandard deviation\b", r"\bsem\b"]),
        ("Data availability described", [r"\bdata availability\b", r"\bavailable data\b", r"\bsupplementary data\b"]),
        ("Code or workflow availability described", [r"\bcode availability\b", r"\bgithub\b", r"\bsoftware\b", r"\bworkflow\b"]),
    ]
    if domain in {"chemistry", "chem_bio"}:
        checks.extend(
            [
                ("Chemical identity evidence described", [r"\bsmiles\b", r"\binchi\b", r"\bnmr\b", r"\blc-ms\b", r"\bhrms\b"]),
                ("Yield or conversion reported", [r"\byield\b", r"\bconversion\b", r"\bselectivity\b"]),
            ]
        )
    if domain in {"biology", "chem_bio"}:
        checks.extend(
            [
                ("Biological system described", [r"\bcell line\b", r"\bspecies\b", r"\bstrain\b", r"\borganism\b"]),
                ("Assay conditions described", [r"\bassay\b", r"\bdose\b", r"\bconcentration\b", r"\bincubat"]),
            ]
        )

    return [_check_item(item, patterns, text, sections, source_path) for item, patterns in checks]


def _check_item(
    item: str,
    patterns: list[str],
    text: str,
    sections: list[PaperSection],
    source_path: str | None,
) -> ReproducibilityChecklistItem:
    lowered = text.lower()
    matched_pattern = next((pattern for pattern in patterns if re.search(pattern, lowered, re.IGNORECASE)), None)
    if not matched_pattern:
        return ReproducibilityChecklistItem(
            item=item,
            status="missing",
            rationale="No clear textual signal found.",
        )

    evidence = _find_evidence(patterns, sections, source_path)
    return ReproducibilityChecklistItem(
        item=item,
        status="present",
        rationale="Detected textual signal in paper.",
        evidence=evidence,
    )


def _build_strengths(
    checklist: list[ReproducibilityChecklistItem],
    sections: list[PaperSection],
    source_path: str | None,
) -> list[ReviewFinding]:
    strengths: list[ReviewFinding] = []
    present = [item for item in checklist if item.status == "present"]
    if present:
        strengths.append(
            ReviewFinding(
                category="reproducibility",
                severity="info",
                finding=f"Detected {len(present)} reproducibility signals.",
                evidence=[item.evidence for item in present if item.evidence][:4],
            )
        )
    section_names = {section.name.lower() for section in sections}
    if {"methods", "results"} & section_names or {"materials And Methods".lower(), "results"} & section_names:
        strengths.append(
            ReviewFinding(
                category="structure",
                severity="info",
                finding="Paper appears to include method and result-oriented sections.",
                evidence=[],
            )
        )
    if not strengths:
        strengths.append(
            ReviewFinding(
                category="triage",
                severity="low",
                finding="No strong deterministic quality signals were detected; manual review is recommended.",
                evidence=[],
            )
        )
    return strengths


def _build_limitations(
    text: str,
    sections: list[PaperSection],
    checklist: list[ReproducibilityChecklistItem],
    claims: list[PaperClaim],
    domain: str,
    source_path: str | None,
) -> list[ReviewFinding]:
    limitations: list[ReviewFinding] = []
    for item in checklist:
        if item.status == "missing":
            severity = "medium" if item.item in {"Controls or baselines described", "Replicates or sample size described"} else "low"
            limitations.append(
                ReviewFinding(
                    category="reproducibility",
                    severity=severity,
                    finding=f"Missing signal: {item.item}.",
                    evidence=[],
                )
            )

    explicit_limitations = _section_by_name(sections, "limitations")
    if explicit_limitations:
        limitations.append(
            ReviewFinding(
                category="authors_limitations",
                severity="info",
                finding="Paper includes an explicit limitations section.",
                evidence=[
                    EvidenceSpan(
                        text=_first_sentences(explicit_limitations.text, 2),
                        section=explicit_limitations.name,
                        source_path=source_path,
                    )
                ],
            )
        )

    overclaims = [
        claim
        for claim in claims
        if any(term in claim.claim.lower() for term in OVERCLAIM_TERMS)
    ]
    if overclaims:
        limitations.append(
            ReviewFinding(
                category="overclaiming",
                severity="high",
                finding="Potentially overconfident or promotional claim language detected.",
                evidence=[claim.evidence for claim in overclaims if claim.evidence][:5],
            )
        )

    if domain in {"chemistry", "chem_bio"} and not re.search(r"\b(smiles|inchi|nmr|lc-ms|hrms|yield)\b", text, re.IGNORECASE):
        limitations.append(
            ReviewFinding(
                category="chemistry_reporting",
                severity="medium",
                finding="No obvious chemical identity or yield reporting signal was detected.",
                evidence=[],
            )
        )

    return limitations


def _answer_focus_questions(
    focus_questions: list[str],
    text: str,
    sections: list[PaperSection],
    source_path: str | None,
) -> list[ReviewFinding]:
    notes: list[ReviewFinding] = []
    for question in focus_questions:
        keywords = [word for word in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", question.lower()) if word not in {"what", "where", "when", "does", "this", "paper", "study"}]
        evidence = _find_evidence([re.escape(keyword) for keyword in keywords[:5]], sections, source_path) if keywords else None
        notes.append(
            ReviewFinding(
                category="focus_question",
                severity="info" if evidence else "low",
                finding=f"Focus question: {question}",
                evidence=[evidence] if evidence else [],
            )
        )
    return notes


def _recommend(
    limitations: list[ReviewFinding],
    checklist: list[ReproducibilityChecklistItem],
    claims: list[PaperClaim],
) -> str:
    high_count = sum(1 for finding in limitations if finding.severity == "high")
    medium_count = sum(1 for finding in limitations if finding.severity == "medium")
    missing_count = sum(1 for item in checklist if item.status == "missing")
    if high_count or medium_count >= 4 or missing_count >= 6:
        return "high_risk"
    if medium_count >= 1 or missing_count >= 3 or not claims:
        return "needs_manual_review"
    return "ready_for_triage"


def _make_summary(
    metadata: PaperMetadata,
    claims: list[PaperClaim],
    strengths: list[ReviewFinding],
    limitations: list[ReviewFinding],
    recommendation: str,
) -> str:
    title = metadata.title or "Untitled paper"
    return (
        f"{title}: detected {len(claims)} claim-like statements, "
        f"{len(strengths)} strengths, and {len(limitations)} limitations. "
        f"Deterministic recommendation: {recommendation}."
    )


def _find_evidence(patterns: list[str], sections: list[PaperSection], source_path: str | None) -> EvidenceSpan | None:
    for section in sections:
        for sentence in _sentences(section.text):
            if any(re.search(pattern, sentence, re.IGNORECASE) for pattern in patterns):
                return EvidenceSpan(text=sentence, section=section.name, source_path=source_path)
    return None


def _section_by_name(sections: list[PaperSection], name: str) -> PaperSection | None:
    return next((section for section in sections if section.name.lower() == name.lower()), None)


def _sentences(text: str) -> list[str]:
    candidates = re.split(r"(?<=[.!?])\s+", _normalize_text(text))
    return [candidate.strip() for candidate in candidates if 30 <= len(candidate.strip()) <= 700]


def _first_sentences(text: str, count: int) -> str:
    return " ".join(_sentences(text)[:count]) or text[:500]


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))
