from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hackathon_agents.tools.literature_tools import (
    build_evidence_table,
    deduplicate_literature_records,
    extract_key_terms,
    format_citations,
    rank_literature_records,
    search_local_corpus,
)


class LiteratureToolsTests(unittest.TestCase):
    def test_search_local_corpus_ranks_matching_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "photoredox.md").write_text("Photoredox reactions show light-intensity effects.", encoding="utf-8")
            (root / "enzymes.md").write_text("Enzyme kinetics can saturate with substrate.", encoding="utf-8")

            result = search_local_corpus({"query": "light intensity photoredox", "corpus_dir": str(root), "limit": 1})

        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(result.data["records"]), 1)
        self.assertEqual(result.data["records"][0]["title"], "photoredox")

    def test_build_evidence_table_labels_direct_support(self) -> None:
        result = build_evidence_table(
            {
                "claims": ["Light intensity controls radical photoredox kinetics"],
                "snippets": ["Photoredox radical reactions show strong light intensity effects."],
            }
        )

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["rows"][0]["support"], "direct")

    def test_format_citations_compact(self) -> None:
        result = format_citations(
            {
                "records": [
                    {
                        "authors": ["A. Curie", "B. Meitner"],
                        "year": 2026,
                        "title": "Mechanistic controls",
                        "journal": "J. Tests",
                    }
                ]
            }
        )

        self.assertTrue(result.ok, result.error)
        self.assertIn("Mechanistic controls", result.data["citations"][0])

    def test_rank_literature_records_uses_query_and_filters(self) -> None:
        result = rank_literature_records(
            {
                "query": "photoredox radical kinetics",
                "records": [
                    {"title": "Photoredox radical kinetics", "abstract": "Light controls radical rates.", "year": 2025},
                    {"title": "Unrelated protein folding", "abstract": "A structural biology paper.", "year": 2025},
                ],
                "limit": 1,
            }
        )

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["records"][0]["title"], "Photoredox radical kinetics")

    def test_deduplicate_literature_records_by_doi(self) -> None:
        result = deduplicate_literature_records(
            {
                "records": [
                    {"title": "A", "doi": "10.1000/test"},
                    {"title": "A duplicate", "doi": "10.1000/test"},
                    {"title": "B", "doi": "10.1000/other"},
                ]
            }
        )

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["unique_count"], 2)
        self.assertEqual(result.data["duplicate_count"], 1)

    def test_extract_key_terms_returns_bigrams(self) -> None:
        result = extract_key_terms({"texts": ["photoredox radical kinetics photoredox radical"], "top_n": 3})

        self.assertTrue(result.ok, result.error)
        terms = [item["term"] for item in result.data["terms"]]
        self.assertIn("photoredox radical", terms)


if __name__ == "__main__":
    unittest.main()
