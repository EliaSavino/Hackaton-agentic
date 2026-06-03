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
        self.assertEqual(config.models["local_large"].provider, "ollama")
        self.assertIn("chemist", config.agents)

    def test_router_offline_selects_ollama(self) -> None:
        config = load_config(Path("configs"), run_mode="offline")
        router = ModelRouter(config)
        selection = router.select_for_agent("chemist")
        self.assertEqual(selection.provider, "ollama")


if __name__ == "__main__":
    unittest.main()
