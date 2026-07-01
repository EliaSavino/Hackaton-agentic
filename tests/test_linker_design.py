from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hackathon_agents.schemas.linkers import LinkerDesignRequest
from hackathon_agents.tools.linker_design import (
    design_adc_linkers,
    generate_linker_candidates,
    load_reference_linker_corpus,
    score_linker_candidate,
)


class LinkerDesignTests(unittest.TestCase):
    def test_generate_linker_candidates_can_exclude_reference_controls(self) -> None:
        request = LinkerDesignRequest(include_reference_controls=False)

        candidates = generate_linker_candidates(request)

        self.assertGreaterEqual(len(candidates), 5)
        self.assertTrue(all(not candidate.reference_control for candidate in candidates))
        self.assertTrue(any("oligonucleotide" in candidate.compatible_payload_classes for candidate in candidates))

    def test_score_linker_candidate_adds_adc_specific_proof_points(self) -> None:
        request = LinkerDesignRequest(include_reference_controls=False)
        references, warnings = load_reference_linker_corpus()
        candidate = generate_linker_candidates(request)[0]

        scored = score_linker_candidate(candidate, request, references)

        self.assertFalse(warnings)
        self.assertIsNotNone(scored.scorecard)
        self.assertGreater(scored.scorecard.overall, 0.6)  # type: ignore[union-attr]
        proof_names = {proof.name for proof in scored.proof_points}
        self.assertIn("Circulation stability", proof_names)
        self.assertIn("Tumor or lysosomal release", proof_names)
        self.assertIn("Payload compatibility", proof_names)

    def test_design_adc_linkers_writes_ranked_dossier_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = design_adc_linkers(
                {
                    "output_dir": tmp,
                    "max_candidates": 6,
                    "payload_classes": ["cytotoxin", "oligonucleotide", "immunomodulator"],
                }
            )
            payload = json.loads((Path(tmp) / "linker_candidates.json").read_text(encoding="utf-8"))
            rankings_exists = (Path(tmp) / "linker_rankings.csv").exists()
            report_exists = (Path(tmp) / "linker_design_report.md").exists()
            index_exists = (Path(tmp) / "artifact_index.json").exists()

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["candidate_count"], 6)
        self.assertTrue(rankings_exists)
        self.assertTrue(report_exists)
        self.assertTrue(index_exists)
        self.assertEqual(payload["candidate_count"], 6)
        top = result.data["top_candidate"]
        self.assertGreater(top["scorecard"]["overall"], 0.6)
        self.assertGreaterEqual(len(top["proof_points"]), 6)

    def test_load_reference_linker_corpus_reads_custom_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corpus.json"
            path.write_text(
                json.dumps(
                    {
                        "linker_classes": [
                            {
                                "name": "Test linker",
                                "linker_class": "test",
                                "triggers": ["test trigger"],
                                "conjugation_handles": ["maleimide"],
                                "payload_handles": ["amine"],
                                "release_logic": "Test release logic.",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            records, warnings = load_reference_linker_corpus(path)

        self.assertFalse(warnings)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].name, "Test linker")


if __name__ == "__main__":
    unittest.main()
