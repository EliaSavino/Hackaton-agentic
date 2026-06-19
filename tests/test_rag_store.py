from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hackathon_agents.llm.prompt_terminal import build_prompt_messages
from hackathon_agents.rag import RAGStore
from hackathon_agents.tools.rag_tools import build_rag_context, ingest_rag_documents, search_rag


class RAGStoreTests(unittest.TestCase):
    def test_ingest_and_search_persistent_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus = root / "corpus"
            corpus.mkdir()
            db_path = root / "rag.sqlite"
            (corpus / "photoredox.md").write_text(
                "Photoredox radical reactions show strong light intensity effects. "
                "Catalyst loading changes the kinetic profile.",
                encoding="utf-8",
            )
            (corpus / "enzymes.md").write_text(
                "Enzyme kinetics saturate with substrate concentration and temperature.",
                encoding="utf-8",
            )

            ingest = ingest_rag_documents(
                {
                    "path": str(corpus),
                    "db_path": str(db_path),
                    "chunk_size": 50,
                    "chunk_overlap": 5,
                }
            )
            search = search_rag({"query": "photoredox light intensity", "db_path": str(db_path), "limit": 1})

        self.assertTrue(ingest.ok, ingest.error)
        self.assertEqual(ingest.data["document_count"], 2)
        self.assertTrue(search.ok, search.error)
        self.assertEqual(search.data["records"][0]["title"], "photoredox")

    def test_store_builds_bounded_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "rag.sqlite"
            store = RAGStore(db_path)
            store.ingest_text(
                "Nickel catalysis can use bidentate ligands. Oxidative addition may be rate limiting.",
                title="nickel notes",
                chunk_size=50,
                chunk_overlap=0,
            )

            result = build_rag_context(
                {
                    "query": "nickel oxidative addition",
                    "db_path": str(db_path),
                    "limit": 2,
                    "max_chars": 300,
                }
            )

        self.assertTrue(result.ok, result.error)
        self.assertIn("nickel notes", result.data["context"])
        self.assertLessEqual(len(result.data["context"]), 300)

    def test_prompt_messages_wrap_rag_context(self) -> None:
        messages = build_prompt_messages(
            "What controls the rate?",
            system_prompt="Be concise.",
            history=[{"role": "assistant", "content": "Prior answer"}],
            rag_context="[1] kinetics\nLight intensity changes rate.",
        )

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("<retrieved_context>", messages[-1]["content"])
        self.assertIn("What controls the rate?", messages[-1]["content"])


if __name__ == "__main__":
    unittest.main()
