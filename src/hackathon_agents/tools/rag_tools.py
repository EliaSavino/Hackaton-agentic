from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hackathon_agents.rag import DEFAULT_RAG_DB_PATH, RAGStore
from hackathon_agents.tools.base import error_result, ok_result


class RAGIngestInput(BaseModel):
    path: str
    db_path: str = str(DEFAULT_RAG_DB_PATH)
    extensions: list[str] = Field(default_factory=lambda: [".txt", ".md", ".markdown", ".pdf", ".docx"])
    chunk_size: int = Field(default=700, ge=50, le=4000)
    chunk_overlap: int = Field(default=100, ge=0, le=1000)
    max_chars: int = Field(default=2_000_000, ge=1, le=10_000_000)
    replace: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGSearchInput(BaseModel):
    query: str = Field(..., min_length=1)
    db_path: str = str(DEFAULT_RAG_DB_PATH)
    limit: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=0.0)


class RAGContextInput(RAGSearchInput):
    max_chars: int = Field(default=4_000, ge=200, le=64_000)


def ingest_rag_documents(input_data: RAGIngestInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, RAGIngestInput) else RAGIngestInput.model_validate(input_data)
    try:
        store = RAGStore(parsed.db_path)
        summary = store.ingest_path(
            parsed.path,
            extensions=parsed.extensions,
            chunk_size=parsed.chunk_size,
            chunk_overlap=parsed.chunk_overlap,
            max_chars=parsed.max_chars,
            replace=parsed.replace,
            metadata=parsed.metadata,
        )
        artifacts = [summary["db_path"]]
        return ok_result(summary, artifacts=artifacts)
    except Exception as exc:
        return error_result(str(exc), {"path": parsed.path, "db_path": parsed.db_path})


def search_rag(input_data: RAGSearchInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, RAGSearchInput) else RAGSearchInput.model_validate(input_data)
    try:
        store = RAGStore(parsed.db_path)
        records = store.search(parsed.query, limit=parsed.limit, min_score=parsed.min_score)
        return ok_result(
            {
                "query": parsed.query,
                "db_path": parsed.db_path,
                "records": [record.model_dump(mode="json") for record in records],
                "record_count": len(records),
            }
        )
    except Exception as exc:
        return error_result(str(exc), {"query": parsed.query, "db_path": parsed.db_path})


def build_rag_context(input_data: RAGContextInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, RAGContextInput) else RAGContextInput.model_validate(input_data)
    try:
        store = RAGStore(parsed.db_path)
        context = store.build_context(parsed.query, limit=parsed.limit, max_chars=parsed.max_chars)
        return ok_result(context)
    except Exception as exc:
        return error_result(str(exc), {"query": parsed.query, "db_path": parsed.db_path})
