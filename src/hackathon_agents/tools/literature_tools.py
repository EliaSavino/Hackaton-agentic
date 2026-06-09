from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from hackathon_agents.tools.base import error_result, ok_result


class LocalCorpusSearchInput(BaseModel):
    query: str = Field(..., min_length=1)
    corpus_dir: str | None = None
    documents: list[dict[str, Any]] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1, le=50)
    extensions: list[str] = Field(default_factory=lambda: [".txt", ".md"])


class EvidenceTableInput(BaseModel):
    claims: list[str] = Field(default_factory=list)
    snippets: list[str] = Field(default_factory=list)
    query: str | None = None
    max_items: int = Field(default=12, ge=1, le=100)


class CitationFormatInput(BaseModel):
    records: list[dict[str, Any]]
    style: Literal["compact", "bibtex"] = "compact"


class LiteratureRecordRankInput(BaseModel):
    query: str = Field(..., min_length=1)
    records: list[dict[str, Any]]
    limit: int = Field(default=10, ge=1, le=100)
    include_terms: list[str] = Field(default_factory=list)
    exclude_terms: list[str] = Field(default_factory=list)
    year_min: int | None = None
    year_max: int | None = None


class LiteratureDedupInput(BaseModel):
    records: list[dict[str, Any]]
    title_similarity_threshold: float = Field(default=0.82, ge=0.0, le=1.0)


class KeyTermExtractionInput(BaseModel):
    texts: list[str] = Field(default_factory=list)
    documents: list[dict[str, Any]] = Field(default_factory=list)
    top_n: int = Field(default=15, ge=1, le=100)
    min_token_length: int = Field(default=3, ge=1, le=20)
    include_bigrams: bool = True


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+-]*")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
}


def search_local_corpus(input_data: LocalCorpusSearchInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, LocalCorpusSearchInput) else LocalCorpusSearchInput.model_validate(input_data)
    try:
        documents = _load_documents(parsed)
        if not documents:
            return ok_result({"query": parsed.query, "records": [], "document_count": 0})

        query_terms = _tokens(parsed.query)
        document_frequencies = _document_frequencies(documents)
        scored = []
        for document in documents:
            text = str(document.get("text", ""))
            tokens = _tokens(text)
            score = _tfidf_score(query_terms, tokens, document_frequencies, len(documents))
            if score <= 0.0:
                continue
            scored.append(
                {
                    "title": document.get("title") or document.get("path") or "untitled",
                    "path": document.get("path"),
                    "score": score,
                    "snippet": _best_snippet(text, query_terms),
                    "metadata": document.get("metadata", {}),
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        return ok_result({"query": parsed.query, "records": scored[: parsed.limit], "document_count": len(documents)})
    except Exception as exc:
        return error_result(str(exc), {"query": parsed.query, "corpus_dir": parsed.corpus_dir})


def build_evidence_table(input_data: EvidenceTableInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, EvidenceTableInput) else EvidenceTableInput.model_validate(input_data)
    try:
        query_terms = set(_tokens(parsed.query or " ".join(parsed.claims)))
        rows = []
        for claim in parsed.claims:
            claim_terms = set(_tokens(claim))
            best_snippet = ""
            best_overlap = 0
            for snippet in parsed.snippets:
                snippet_terms = set(_tokens(snippet))
                overlap = len((claim_terms | query_terms) & snippet_terms)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_snippet = snippet
            rows.append(
                {
                    "claim": claim,
                    "best_evidence": best_snippet,
                    "overlap_terms": best_overlap,
                    "support": _support_label(best_overlap),
                }
            )
        return ok_result({"rows": rows[: parsed.max_items], "claim_count": len(parsed.claims)})
    except Exception as exc:
        return error_result(str(exc), {"claim_count": len(parsed.claims), "snippet_count": len(parsed.snippets)})


def format_citations(input_data: CitationFormatInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, CitationFormatInput) else CitationFormatInput.model_validate(input_data)
    try:
        if parsed.style == "bibtex":
            citations = [_bibtex(record, index) for index, record in enumerate(parsed.records, start=1)]
        else:
            citations = [_compact_citation(record) for record in parsed.records]
        return ok_result({"citations": citations, "count": len(citations), "style": parsed.style})
    except Exception as exc:
        return error_result(str(exc), {"style": parsed.style})


def rank_literature_records(input_data: LiteratureRecordRankInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, LiteratureRecordRankInput) else LiteratureRecordRankInput.model_validate(input_data)
    try:
        records = [_with_record_text(record) for record in parsed.records]
        if not records:
            return ok_result({"query": parsed.query, "records": [], "record_count": 0})
        document_frequencies = _document_frequencies(records)
        query_terms = _tokens(parsed.query)
        include_terms = set(_tokens(" ".join(parsed.include_terms)))
        exclude_terms = set(_tokens(" ".join(parsed.exclude_terms)))
        ranked = []
        for index, record in enumerate(records):
            year = _record_year(record)
            if parsed.year_min is not None and year is not None and year < parsed.year_min:
                continue
            if parsed.year_max is not None and year is not None and year > parsed.year_max:
                continue
            tokens = _tokens(record["text"])
            token_set = set(tokens)
            score = _tfidf_score(query_terms, tokens, document_frequencies, len(records))
            score += 0.04 * len(include_terms & token_set)
            score -= 0.08 * len(exclude_terms & token_set)
            if score <= 0.0:
                continue
            ranked.append(
                {
                    **{key: value for key, value in record.items() if key != "text"},
                    "rank": 0,
                    "input_index": index,
                    "score": score,
                    "matched_terms": sorted(set(query_terms) & token_set),
                    "screening_flags": _screening_flags(token_set, include_terms, exclude_terms),
                }
            )
        ranked.sort(key=lambda item: item["score"], reverse=True)
        for rank, record in enumerate(ranked, start=1):
            record["rank"] = rank
        return ok_result({"query": parsed.query, "records": ranked[: parsed.limit], "record_count": len(records)})
    except Exception as exc:
        return error_result(str(exc), {"query": parsed.query, "record_count": len(parsed.records)})


def deduplicate_literature_records(input_data: LiteratureDedupInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, LiteratureDedupInput) else LiteratureDedupInput.model_validate(input_data)
    try:
        kept: list[dict[str, Any]] = []
        duplicate_groups: list[dict[str, Any]] = []
        for index, record in enumerate(parsed.records):
            duplicate_index = _find_duplicate_index(record, kept, parsed.title_similarity_threshold)
            if duplicate_index is None:
                kept.append({**record, "input_indices": [index]})
                continue
            kept[duplicate_index]["input_indices"].append(index)
            duplicate_groups.append(
                {
                    "kept_index": duplicate_index,
                    "duplicate_input_index": index,
                    "kept_title": kept[duplicate_index].get("title"),
                    "duplicate_title": record.get("title"),
                    "reason": _duplicate_reason(record, kept[duplicate_index]),
                }
            )
        return ok_result(
            {
                "records": kept,
                "input_count": len(parsed.records),
                "unique_count": len(kept),
                "duplicate_count": len(parsed.records) - len(kept),
                "duplicate_groups": duplicate_groups,
            }
        )
    except Exception as exc:
        return error_result(str(exc), {"record_count": len(parsed.records)})


def extract_key_terms(input_data: KeyTermExtractionInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, KeyTermExtractionInput) else KeyTermExtractionInput.model_validate(input_data)
    try:
        texts = list(parsed.texts) + [str(document.get("text", "")) for document in parsed.documents]
        tokenized = [[token for token in _tokens(text) if len(token) >= parsed.min_token_length] for text in texts]
        if not any(tokenized):
            return ok_result({"terms": [], "document_count": len(texts)})
        term_counts: Counter[str] = Counter()
        document_frequencies: Counter[str] = Counter()
        for tokens in tokenized:
            terms = list(tokens)
            if parsed.include_bigrams:
                terms.extend(f"{left} {right}" for left, right in zip(tokens, tokens[1:]))
            term_counts.update(terms)
            document_frequencies.update(set(terms))
        document_count = max(1, len(texts))
        scored = []
        for term, count in term_counts.items():
            idf = math.log((1 + document_count) / (1 + document_frequencies[term])) + 1.0
            scored.append({"term": term, "count": count, "score": count * idf})
        scored.sort(key=lambda item: (item["score"], item["count"], item["term"]), reverse=True)
        return ok_result({"terms": scored[: parsed.top_n], "document_count": len(texts)})
    except Exception as exc:
        return error_result(str(exc), {"text_count": len(parsed.texts), "document_count": len(parsed.documents)})


def _load_documents(input_data: LocalCorpusSearchInput) -> list[dict[str, Any]]:
    documents = list(input_data.documents)
    if input_data.corpus_dir:
        root = Path(input_data.corpus_dir)
        allowed = {extension.lower() for extension in input_data.extensions}
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in allowed:
                documents.append(
                    {
                        "title": path.stem.replace("_", " "),
                        "path": str(path),
                        "text": path.read_text(encoding="utf-8", errors="ignore"),
                    }
                )
    return documents


def _tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(text) if match.group(0).lower() not in _STOPWORDS]


def _document_frequencies(documents: list[dict[str, Any]]) -> Counter[str]:
    frequencies: Counter[str] = Counter()
    for document in documents:
        frequencies.update(set(_tokens(str(document.get("text", "")))))
    return frequencies


def _tfidf_score(query_terms: list[str], document_tokens: list[str], document_frequencies: Counter[str], document_count: int) -> float:
    if not query_terms or not document_tokens:
        return 0.0
    token_counts = Counter(document_tokens)
    score = 0.0
    for term in query_terms:
        tf = token_counts[term] / len(document_tokens)
        idf = math.log((1 + document_count) / (1 + document_frequencies.get(term, 0))) + 1.0
        score += tf * idf
    return score


def _best_snippet(text: str, query_terms: list[str], window: int = 240) -> str:
    if not text:
        return ""
    lower = text.lower()
    positions = [lower.find(term) for term in query_terms if lower.find(term) >= 0]
    start = max(0, min(positions) - window // 3) if positions else 0
    snippet = text[start : start + window].strip()
    return re.sub(r"\s+", " ", snippet)


def _support_label(overlap: int) -> str:
    if overlap >= 4:
        return "direct"
    if overlap >= 2:
        return "partial"
    if overlap == 1:
        return "weak"
    return "missing"


def _compact_citation(record: dict[str, Any]) -> str:
    authors = record.get("authors") or record.get("author") or "Unknown"
    if isinstance(authors, list):
        author_text = ", ".join(str(author) for author in authors[:3])
        if len(authors) > 3:
            author_text += " et al."
    else:
        author_text = str(authors)
    year = record.get("year") or "n.d."
    title = record.get("title") or "Untitled"
    venue = record.get("journal") or record.get("venue") or ""
    doi = record.get("doi")
    suffix = f" {venue}." if venue else ""
    if doi:
        suffix += f" doi:{doi}"
    return f"{author_text} ({year}). {title}.{suffix}".strip()


def _bibtex(record: dict[str, Any], index: int) -> str:
    key_seed = str(record.get("title") or f"record{index}")
    key = re.sub(r"[^A-Za-z0-9]+", "", key_seed.title())[:32] or f"record{index}"
    authors = record.get("authors") or record.get("author") or "Unknown"
    if isinstance(authors, list):
        authors = " and ".join(str(author) for author in authors)
    fields = {
        "title": record.get("title") or "Untitled",
        "author": authors,
        "year": record.get("year") or "",
        "journal": record.get("journal") or record.get("venue") or "",
        "doi": record.get("doi") or "",
    }
    body = "\n".join(f"  {name} = {{{value}}}," for name, value in fields.items() if value)
    return f"@article{{{key},\n{body}\n}}"


def _with_record_text(record: dict[str, Any]) -> dict[str, Any]:
    return {**record, "text": _record_text(record)}


def _record_text(record: dict[str, Any]) -> str:
    parts = [
        record.get("title"),
        record.get("abstract"),
        record.get("summary"),
        record.get("journal"),
        record.get("venue"),
        " ".join(str(keyword) for keyword in record.get("keywords", []) or []),
    ]
    return " ".join(str(part) for part in parts if part)


def _record_year(record: dict[str, Any]) -> int | None:
    year = record.get("year")
    try:
        return int(year) if year not in (None, "") else None
    except Exception:
        return None


def _screening_flags(token_set: set[str], include_terms: set[str], exclude_terms: set[str]) -> list[str]:
    flags = []
    missing_include = include_terms - token_set
    matched_exclude = exclude_terms & token_set
    if missing_include:
        flags.append(f"missing_include_terms:{','.join(sorted(missing_include))}")
    if matched_exclude:
        flags.append(f"matched_exclude_terms:{','.join(sorted(matched_exclude))}")
    return flags


def _find_duplicate_index(record: dict[str, Any], kept: list[dict[str, Any]], threshold: float) -> int | None:
    doi = _normalize_identifier(record.get("doi"))
    title_terms = set(_tokens(str(record.get("title", ""))))
    for index, candidate in enumerate(kept):
        candidate_doi = _normalize_identifier(candidate.get("doi"))
        if doi and candidate_doi and doi == candidate_doi:
            return index
        candidate_title_terms = set(_tokens(str(candidate.get("title", ""))))
        if title_terms and candidate_title_terms and _jaccard(title_terms, candidate_title_terms) >= threshold:
            return index
    return None


def _duplicate_reason(record: dict[str, Any], candidate: dict[str, Any]) -> str:
    doi = _normalize_identifier(record.get("doi"))
    candidate_doi = _normalize_identifier(candidate.get("doi"))
    if doi and candidate_doi and doi == candidate_doi:
        return "doi"
    return "title_similarity"


def _normalize_identifier(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
