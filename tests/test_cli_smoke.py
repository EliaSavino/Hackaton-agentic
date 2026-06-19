from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


class CLISmokeTests(unittest.TestCase):
    def test_module_help_runs_from_source_tree(self) -> None:
        result = _run_cli("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Scientific-discovery multi-agent workbench", result.stdout)

    def test_mechanism_help_exposes_integration_flags(self) -> None:
        result = _run_cli("mechanism-loop", "--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--literature-corpus-dir", result.stdout)
        self.assertIn("--dft-structure-file", result.stdout)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    return subprocess.run(
        [sys.executable, "-m", "hackathon_agents.cli", *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )


if __name__ == "__main__":
    unittest.main()
