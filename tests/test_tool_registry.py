from __future__ import annotations

import unittest
from pathlib import Path

from hackathon_agents.config import RunMode, load_config
from hackathon_agents.tools.registry import build_tool_registry, summarize_tool_registry


class ToolRegistryTests(unittest.TestCase):
    def test_registry_contains_planner_affordances(self) -> None:
        config = load_config(Path("configs"), run_mode=RunMode.CHEAP)

        registry = build_tool_registry(config)
        by_name = {entry["name"]: entry for entry in registry}

        self.assertIn("rdkit", by_name)
        self.assertEqual(by_name["rdkit"]["category"], "chemistry_descriptors")
        self.assertIn("SMILES strings", by_name["rdkit"]["inputs"])
        self.assertIn("descriptor dictionaries", by_name["rdkit"]["outputs"])
        self.assertTrue(by_name["rdkit"]["enabled"])

        self.assertIn("orca", by_name)
        self.assertFalse(by_name["orca"]["enabled"])
        self.assertIn("not enabled for run mode", by_name["orca"]["unavailable_reason"])

        self.assertIn("saturn", by_name)
        self.assertTrue(by_name["saturn"]["mock_behavior"])
        self.assertTrue(by_name["saturn"]["mock_safe"])

    def test_registry_summary_counts_enabled_tools(self) -> None:
        config = load_config(Path("configs"), run_mode=RunMode.CHEAP)
        summary = summarize_tool_registry(build_tool_registry(config))

        self.assertGreater(summary["tool_count"], 0)
        self.assertGreater(summary["enabled_count"], 0)
        self.assertIn("rdkit", summary["enabled_tools"])
        self.assertIn("orca", summary["disabled_tools"])
        self.assertIn("chemistry_descriptors", summary["categories"])


if __name__ == "__main__":
    unittest.main()
