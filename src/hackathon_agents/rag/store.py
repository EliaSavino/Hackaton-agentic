from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from hackathon_agents.tools.paper_review import load_paper_text


DEFAULT_RAG_DB_PATH = Path("data/rag.sqlite")
DEFAULT_EXTENSIONS = [".txt", ".md", ".markdown", ".pdf", ".docx"]

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
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
}


class RAGSearchResult(BaseModel):
    chunk_id: int
    document_id: int
    chunk_index: int
    title: str
    source_path: str | None = None
    source_type: str = "unknown"
    score: float
    text: str
    snippet: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGStore:
    """Small SQLite-backed lexical retrieval store for local RAG workflows."""

    def __init__(self, db_path: str | Path = DEFAULT_RAG_DB_PATH):
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY,
                    source_path TEXT UNIQUE,
                    title TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    char_count INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY,
                    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(document_id, chunk_index)
                );

                CREATE TABLE IF NOT EXISTS chunk_terms (
                    chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
                    term TEXT NOT NULL,
                    count INTEGER NOT NULL,
                    PRIMARY KEY(chunk_id, term)
                );

                CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
                CREATE INDEX IF NOT EXISTS idx_chunk_terms_term ON chunk_terms(term);
                """
            )

    def ingest_path(
        self,
        path: str | Path,
        *,
        extensions: list[str] | None = None,
        chunk_size: int = 700,
        chunk_overlap: int = 100,
        max_chars: int = 2_000_000,
        replace: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        root = Path(path)
        if not root.exists():
            raise FileNotFoundError(f"RAG ingest path does not exist: {root}")

        allowed = {extension.lower() for extension in (extensions or DEFAULT_EXTENSIONS)}
        paths = [root] if root.is_file() else [item for item in sorted(root.rglob("*")) if item.is_file()]
        summaries = []
        skipped = []
        for item in paths:
            if item.suffix.lower() not in allowed:
                continue
            try:
                loaded = load_paper_text({"path": str(item), "max_chars": max_chars})
                if not loaded.ok:
                    skipped.append({"path": str(item), "error": loaded.error})
                    continue
                summaries.append(
                    self.ingest_text(
                        loaded.data["text"],
                        title=item.stem.replace("_", " "),
                        source_path=str(item),
                        source_type=loaded.data.get("source_type", item.suffix.lower().lstrip(".") or "text"),
                        metadata=metadata,
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap,
                        replace=replace,
                    )
                )
            except Exception as exc:
                skipped.append({"path": str(item), "error": str(exc)})

        return {
            "db_path": str(self.db_path),
            "document_count": sum(0 if item.get("skipped") else 1 for item in summaries),
            "chunk_count": sum(int(item.get("chunk_count", 0)) for item in summaries),
            "skipped": skipped + [item for item in summaries if item.get("skipped")],
            "documents": summaries,
        }

    def ingest_text(
        self,
        text: str,
        *,
        title: str,
        source_path: str | None = None,
        source_type: str = "text",
        metadata: dict[str, Any] | None = None,
        chunk_size: int = 700,
        chunk_overlap: int = 100,
        replace: bool = True,
    ) -> dict[str, Any]:
        self.initialize()
        normalized = _normalize_text(text)
        content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        now = time.time()
        source_key = source_path or f"memory:{content_hash[:24]}"
        chunks = _chunk_text(normalized, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id, content_hash FROM documents WHERE source_path = ?",
                (source_key,),
            ).fetchone()
            if existing and existing["content_hash"] == content_hash and not replace:
                chunk_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM chunks WHERE document_id = ?",
                    (existing["id"],),
                ).fetchone()["count"]
                return {
                    "db_path": str(self.db_path),
                    "document_id": existing["id"],
                    "title": title,
                    "source_path": source_key,
                    "content_hash": content_hash,
                    "chunk_count": chunk_count,
                    "skipped": True,
                    "reason": "unchanged",
                }

            if existing:
                connection.execute("DELETE FROM documents WHERE id = ?", (existing["id"],))

            cursor = connection.execute(
                """
                INSERT INTO documents (
                    source_path, title, source_type, content_hash, char_count,
                    metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_key,
                    title,
                    source_type,
                    content_hash,
                    len(normalized),
                    json.dumps(metadata or {}, sort_keys=True),
                    now,
                    now,
                ),
            )
            document_id = int(cursor.lastrowid)
            for index, chunk in enumerate(chunks):
                chunk_metadata = {
                    "start_word": chunk["start_word"],
                    "end_word": chunk["end_word"],
                }
                chunk_cursor = connection.execute(
                    """
                    INSERT INTO chunks (document_id, chunk_index, text, token_count, metadata_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        index,
                        chunk["text"],
                        len(_tokens(chunk["text"])),
                        json.dumps(chunk_metadata, sort_keys=True),
                    ),
                )
                chunk_id = int(chunk_cursor.lastrowid)
                term_counts = Counter(_tokens(chunk["text"]))
                connection.executemany(
                    "INSERT INTO chunk_terms (chunk_id, term, count) VALUES (?, ?, ?)",
                    [(chunk_id, term, count) for term, count in sorted(term_counts.items())],
                )

        return {
            "db_path": str(self.db_path),
            "document_id": document_id,
            "title": title,
            "source_path": source_key,
            "source_type": source_type,
            "content_hash": content_hash,
            "char_count": len(normalized),
            "chunk_count": len(chunks),
            "skipped": False,
        }

    def search(self, query: str, *, limit: int = 5, min_score: float = 0.0) -> list[RAGSearchResult]:
        self.initialize()
        query_terms = _dedupe(_tokens(query))
        if not query_terms:
            return []

        with self._connect() as connection:
            total_chunks = int(connection.execute("SELECT COUNT(*) AS count FROM chunks").fetchone()["count"])
            if total_chunks == 0:
                return []

            placeholders = ", ".join("?" for _ in query_terms)
            term_rows = connection.execute(
                f"""
                SELECT chunk_id, term, count
                FROM chunk_terms
                WHERE term IN ({placeholders})
                """,
                query_terms,
            ).fetchall()
            if not term_rows:
                return []

            doc_frequency_rows = connection.execute(
                f"""
                SELECT term, COUNT(*) AS frequency
                FROM chunk_terms
                WHERE term IN ({placeholders})
                GROUP BY term
                """,
                query_terms,
            ).fetchall()
            document_frequencies = {row["term"]: int(row["frequency"]) for row in doc_frequency_rows}
            counts_by_chunk: dict[int, dict[str, int]] = defaultdict(dict)
            for row in term_rows:
                counts_by_chunk[int(row["chunk_id"])][row["term"]] = int(row["count"])

            chunk_ids = list(counts_by_chunk)
            chunk_placeholders = ", ".join("?" for _ in chunk_ids)
            rows = connection.execute(
                f"""
                SELECT
                    chunks.id AS chunk_id,
                    chunks.document_id AS document_id,
                    chunks.chunk_index AS chunk_index,
                    chunks.text AS text,
                    chunks.token_count AS token_count,
                    chunks.metadata_json AS chunk_metadata_json,
                    documents.title AS title,
                    documents.source_path AS source_path,
                    documents.source_type AS source_type,
                    documents.metadata_json AS document_metadata_json
                FROM chunks
                JOIN documents ON documents.id = chunks.document_id
                WHERE chunks.id IN ({chunk_placeholders})
                """,
                chunk_ids,
            ).fetchall()

        scored: list[RAGSearchResult] = []
        query_phrase = query.lower().strip()
        for row in rows:
            chunk_id = int(row["chunk_id"])
            token_count = max(1, int(row["token_count"]))
            score = 0.0
            for term, count in counts_by_chunk[chunk_id].items():
                idf = math.log((1 + total_chunks) / (1 + document_frequencies.get(term, 0))) + 1.0
                score += (1.0 + math.log(count)) * idf
            score = score / math.sqrt(token_count)
            text = row["text"]
            if query_phrase and query_phrase in text.lower():
                score += 0.75
            if score < min_score:
                continue
            metadata = _json_object(row["document_metadata_json"])
            metadata.update(_json_object(row["chunk_metadata_json"]))
            scored.append(
                RAGSearchResult(
                    chunk_id=chunk_id,
                    document_id=int(row["document_id"]),
                    chunk_index=int(row["chunk_index"]),
                    title=row["title"],
                    source_path=row["source_path"],
                    source_type=row["source_type"],
                    score=score,
                    text=text,
                    snippet=_best_snippet(text, query_terms),
                    metadata=metadata,
                )
            )

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:limit]

    def build_context(self, query: str, *, limit: int = 5, max_chars: int = 4_000) -> dict[str, Any]:
        results = self.search(query, limit=limit)
        blocks: list[str] = []
        remaining = max_chars
        for index, result in enumerate(results, start=1):
            source = result.source_path or result.title
            header = f"[{index}] {result.title} ({source}, chunk {result.chunk_index}, score {result.score:.3f})"
            body = result.text.strip()
            block = f"{header}\n{body}"
            if len(block) > remaining:
                block = block[: max(0, remaining - 3)].rstrip() + "..."
            if not block.strip():
                continue
            blocks.append(block)
            remaining -= len(block) + 2
            if remaining <= 0:
                break
        return {
            "query": query,
            "context": "\n\n".join(blocks),
            "results": [result.model_dump(mode="json") for result in results],
            "result_count": len(results),
            "max_chars": max_chars,
        }

    def stats(self) -> dict[str, Any]:
        self.initialize()
        with self._connect() as connection:
            documents = int(connection.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"])
            chunks = int(connection.execute("SELECT COUNT(*) AS count FROM chunks").fetchone()["count"])
        return {"db_path": str(self.db_path), "document_count": documents, "chunk_count": chunks}

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(text) if match.group(0).lower() not in _STOPWORDS]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _chunk_text(text: str, *, chunk_size: int, chunk_overlap: int) -> list[dict[str, Any]]:
    if chunk_size < 50:
        raise ValueError("chunk_size must be at least 50 words.")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap cannot be negative.")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size.")

    words = text.split()
    if not words:
        return [{"text": "", "start_word": 0, "end_word": 0}]

    chunks = []
    step = chunk_size - chunk_overlap
    start = 0
    while start < len(words):
        end = min(len(words), start + chunk_size)
        chunks.append(
            {
                "text": " ".join(words[start:end]),
                "start_word": start,
                "end_word": end,
            }
        )
        if end >= len(words):
            break
        start += step
    return chunks


def _json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _best_snippet(text: str, query_terms: list[str], window: int = 320) -> str:
    if not text:
        return ""
    lower = text.lower()
    positions = [lower.find(term) for term in query_terms if lower.find(term) >= 0]
    start = max(0, min(positions) - window // 3) if positions else 0
    snippet = text[start : start + window].strip()
    return re.sub(r"\s+", " ", snippet)
