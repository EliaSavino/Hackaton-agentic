from __future__ import annotations

import unittest
from pathlib import Path


class HPCDocsTests(unittest.TestCase):
    def test_hpc_guide_links_checked_in_mechanism_slurm_template(self) -> None:
        root = Path(__file__).resolve().parents[1]
        guide = (root / "docs" / "hpc.md").read_text(encoding="utf-8")
        template_path = root / "docs" / "examples" / "run_mechanism_once.slurm"
        template = template_path.read_text(encoding="utf-8")

        self.assertIn("docs/examples/run_mechanism_once.slurm", guide)
        self.assertIn("sbatch docs/examples/run_mechanism_once.slurm", guide)
        self.assertIn("python -m hackathon_agents.cli mechanism-once", template)
        self.assertIn("#SBATCH --output=hackathon_mechanism_%j.out", template)
        self.assertIn('export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"', template)
        self.assertIn('MODE="${MECHANISM_MODE:-mock}"', template)
        self.assertIn("--run-root", template)


if __name__ == "__main__":
    unittest.main()
