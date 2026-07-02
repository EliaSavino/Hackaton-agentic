from __future__ import annotations

import unittest
from pathlib import Path

from hackathon_agents.config import RunMode, load_config
from hackathon_agents.llm.router import ModelRouter


class ConfigTests(unittest.TestCase):
    def test_load_default_configs(self) -> None:
        config = load_config(Path("configs"), run_mode="cheap")
        self.assertEqual(config.run_mode, RunMode.CHEAP)
        self.assertIn("local_large", config.models)
        self.assertEqual(config.models["local_large"].provider, "anthropic")
        self.assertEqual(config.models["local_large"].model, config.models["local_large"].model)
        self.assertIn("chemist", config.agents)
        self.assertIn("latex_writer", config.tools)
        self.assertIn("latex", config.models["local_small"].capabilities)
        self.assertIn("memory_writer", config.tools)
        self.assertEqual(config.tools["memory_writer"].jsonl_path, "data/memory/project_memory.jsonl")
        self.assertIn("robrains_bo", config.tools)
        self.assertEqual(config.tools["robrains_bo"].repo_path, "/Users/es/GitHub/RoBrains")

    def test_router_offline_uses_configured_provider(self) -> None:
        config = load_config(Path("configs"), run_mode="offline")
        router = ModelRouter(config)
        selection = router.select_for_agent("chemist")
        self.assertEqual(selection.provider, config.model_routing.offline_required_provider)
        self.assertEqual(selection.model, config.models["local_large"].model)


if __name__ == "__main__":
    unittest.main()
