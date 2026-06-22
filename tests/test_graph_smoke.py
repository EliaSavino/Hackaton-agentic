from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hackathon_agents.config import load_config
from hackathon_agents.graph import build_graph
from hackathon_agents.state import DiscoveryStatePayload


class GraphSmokeTests(unittest.TestCase):
    def test_graph_runs_without_dft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(Path("configs"), run_mode="no_dft")
            memory_dir = Path(tmp) / "memory"
            config.tools["memory_writer"].jsonl_path = str(memory_dir / "project_memory.jsonl")
            config.tools["memory_writer"].markdown_path = str(memory_dir / "project_memory.md")
            state = DiscoveryStatePayload(
                original_user_request="Find candidate substrates",
                run_dir=tmp,
                run_mode=config.run_mode,
            )
            final_state = build_graph(config).invoke(state)
            self.assertEqual(final_state.original_user_request, "Find candidate substrates")
            self.assertIsNotNone(final_state.plan)
            self.assertGreater(len(final_state.candidate_molecules), 0)
            self.assertGreaterEqual(final_state.iteration, 1)
            self.assertLessEqual(final_state.iteration, final_state.max_iterations)
            self.assertGreaterEqual(len(final_state.critic_decisions), 1)
            self.assertIsNotNone(final_state.stop_reason)
            self.assertTrue(any(record.tool_name.startswith("rdkit") for record in final_state.tool_results))
            self.assertTrue(Path(tmp, "report.tex").exists())
            self.assertEqual(final_state.metadata.get("latex_report_path"), str(Path(tmp, "report.tex")))
            self.assertTrue(
                any(record.tool_name == "latex_writer.write_latex_report" for record in final_state.tool_results)
            )
            self.assertTrue((memory_dir / "project_memory.jsonl").exists())
            self.assertTrue((memory_dir / "project_memory.md").exists())
            memory_lines = (memory_dir / "project_memory.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertGreaterEqual(len(memory_lines), 5)
            self.assertEqual(final_state.metadata.get("memory_jsonl_path"), str(memory_dir / "project_memory.jsonl"))


if __name__ == "__main__":
    unittest.main()
