from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hackathon_agents.tools.paper_review import load_paper_text, review_paper, split_paper_sections


SAMPLE_PAPER = """
Deterministic Screening of Kinase Inhibitor Candidates
Jane Doe, John Smith
2025

Abstract
This study reports a deterministic screening workflow for kinase inhibitor candidates.
We show that descriptor filtering can prioritize compounds before expensive assays.

Introduction
Kinase inhibitor discovery often requires careful triage of chemical and biological evidence.

Methods
The workflow used a baseline model, positive control, negative control, and triplicate measurements.
The assay used a human cell line with a dose response protocol and concentration range.
Chemical identity was tracked with SMILES strings, LC-MS confirmation, and NMR spectra.
Statistical analysis used p < 0.05 and standard deviation across replicates.

Results
Results show improved ranking of candidates and achieved 72% yield for a reference compound.

Limitations
The study was limited to one cell line and a small candidate set.

Data Availability
Supplementary data and workflow descriptions are available.

Code Availability
The analysis software is available on GitHub.
"""


class PaperReviewTests(unittest.TestCase):
    def test_load_paper_text_from_raw_text(self) -> None:
        result = load_paper_text({"text": SAMPLE_PAPER})
        self.assertTrue(result.ok)
        self.assertIn("Deterministic Screening", result.data["text"])
        self.assertEqual(result.data["source_type"], "text")

    def test_split_paper_sections(self) -> None:
        result = split_paper_sections({"text": SAMPLE_PAPER})
        self.assertTrue(result.ok)
        names = {section["name"] for section in result.data["sections"]}
        self.assertIn("Abstract", names)
        self.assertIn("Methods", names)
        self.assertIn("Results", names)

    def test_review_paper_structured_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "review.json"
            result = review_paper(
                {
                    "text": SAMPLE_PAPER,
                    "domain": "chem_bio",
                    "focus_questions": ["Does the paper describe controls?"],
                    "output_path": str(output),
                }
            )

            self.assertTrue(result.ok)
            self.assertTrue(output.exists())
            review = result.data["review"]
            self.assertEqual(review["metadata"]["title"], "Deterministic Screening of Kinase Inhibitor Candidates")
            self.assertGreaterEqual(len(review["claims"]), 2)
            self.assertGreaterEqual(len(review["reproducibility_checklist"]), 8)
            self.assertIn(review["recommendation"], {"ready_for_triage", "needs_manual_review", "high_risk"})

    def test_missing_path_returns_structured_error(self) -> None:
        result = load_paper_text({"path": "/not/a/real/paper.pdf"})
        self.assertFalse(result.ok)
        self.assertIn("path", result.data)


if __name__ == "__main__":
    unittest.main()
