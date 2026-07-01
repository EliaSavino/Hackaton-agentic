from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hackathon_agents.mechanism.graph import run_mechanism_loop
from hackathon_agents.tools.literature_search import search_literature_prior


class MechanismIntegrationTests(unittest.TestCase):
    def test_literature_prior_can_use_local_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "photoredox.md").write_text(
                "Photoredox radical reactions show strong light intensity effects and dark controls.",
                encoding="utf-8",
            )

            prior = search_literature_prior(
                "photoredox light intensity mechanism",
                mode="mock",
                corpus_dir=str(root),
            )

        self.assertEqual(prior.source, "local")
        self.assertTrue(prior.citations)
        self.assertIn("Photoredox", prior.summary)

    def test_mechanism_loop_accepts_custom_dft_structure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = run_mechanism_loop(
                objective="Infer mechanism for photochemical reaction A + B -> P",
                rounds=1,
                mode="mock",
                run_root=directory,
                dft_structure="N 0.000 0.000 0.000\nH 0.000 0.000 1.000",
            )

        self.assertEqual(state.metadata["dft_structure"], "N 0.000 0.000 0.000\nH 0.000 0.000 1.000")
        if state.dft_jobs:
            self.assertEqual(state.dft_jobs[0].molecule_or_structure, state.metadata["dft_structure"])


if __name__ == "__main__":
    unittest.main()
