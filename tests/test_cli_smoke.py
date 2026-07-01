from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
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

    def test_snellius_gateway_script_cli_generates_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli(
                "snellius-gateway-script",
                "--model-checkpoint",
                "openai/gpt-oss-120b",
                "--output-dir",
                tmp,
                "--vllm-port",
                "8123",
                "--gateway-port",
                "4123",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Script:", result.stdout)
            self.assertTrue((Path(tmp) / "run_snellius_gateway.job").exists())
            self.assertTrue((Path(tmp) / "litellm_config.yaml").exists())
            self.assertTrue((Path(tmp) / "litellm_config.local_only.yaml").exists())

    def test_snellius_client_env_cli_prints_claude_code_env(self) -> None:
        result = _run_cli(
            "snellius-client-env",
            "--snellius-user",
            "alice",
            "--compute-node",
            "gcn31",
            "--local-port",
            "4567",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ssh -N -L 4567:gcn31:4000 alice@snellius.surf.nl", result.stdout)
        self.assertIn("ANTHROPIC_BASE_URL=http://localhost:4567", result.stdout)
        self.assertIn("ANTHROPIC_DEFAULT_SONNET_MODEL=claude-snellius-local", result.stdout)

    def test_system_benchmark_cli_writes_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli("benchmark-system", "--run-root", tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("System benchmark written to", result.stdout)
            benchmark_files = list(Path(tmp).glob("system_benchmark_*/system_benchmark.json"))
            self.assertEqual(len(benchmark_files), 1)
            index_path = benchmark_files[0].parent / "artifact_index.json"
            self.assertTrue(index_path.exists())
            artifact_index = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact_index["provenance"]["workflow"], "system_benchmark")
            self.assertEqual(artifact_index["provenance"]["case_count"], 4)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    env["COLUMNS"] = "120"
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
