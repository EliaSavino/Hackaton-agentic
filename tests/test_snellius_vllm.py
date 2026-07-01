from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hackathon_agents.config import AppConfig, ModelConfig, ModelRoutingConfig, RunMode, load_config
from hackathon_agents.llm.router import ModelRouter
from hackathon_agents.tools.snellius_vllm import (
    generate_snellius_gateway_job,
    generate_snellius_vllm_job,
    render_snellius_client_env,
    render_snellius_litellm_config,
    render_snellius_vllm_job,
)


class SnelliusVLLMTests(unittest.TestCase):
    def test_generate_snellius_vllm_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_snellius_vllm_job(
                {
                    "output_dir": tmp,
                    "model_checkpoint": "meta-llama/Llama-3.1-70B-Instruct",
                    "port": 8123,
                }
            )
            script_path = Path(result.data["script_path"])
            self.assertTrue(script_path.exists())
            script = script_path.read_text(encoding="utf-8")
            self.assertIn("apptainer exec --nv", script)
            self.assertIn("vllm serve", script)
            self.assertIn("--tensor-parallel-size", script)
            self.assertEqual(result.data["base_url"], "http://localhost:8123/v1")

    def test_render_snellius_vllm_script_uses_configured_resources(self) -> None:
        script = render_snellius_vllm_job(
            {
                "output_dir": "unused",
                "model_checkpoint": "test/model",
                "partition": "gpu_h100",
                "gpus_per_node": 2,
                "time_limit": "01:30:00",
            }
        )
        self.assertIn("#SBATCH --partition=gpu_h100", script)
        self.assertIn("#SBATCH --gpus-per-node=2", script)
        self.assertIn("#SBATCH --time=01:30:00", script)

    def test_generate_snellius_gateway_script_and_configs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_snellius_gateway_job(
                {
                    "output_dir": tmp,
                    "model_checkpoint": "openai/gpt-oss-120b",
                    "vllm_port": 8123,
                    "gateway_port": 4123,
                    "local_client_port": 4123,
                    "extra_vllm_args": ["--max-model-len", "8192"],
                }
            )
            script = Path(result.data["script_path"]).read_text(encoding="utf-8")
            full_config = Path(result.data["litellm_config_path"]).read_text(encoding="utf-8")
            local_only_config = Path(result.data["local_only_litellm_config_path"]).read_text(encoding="utf-8")

        self.assertIn("VLLM_HOST=127.0.0.1", script)
        self.assertIn("GATEWAY_PORT=4123", script)
        self.assertIn('DOWNLOAD_DIR="$TMPDIR/vllm_downloads"', script)
        self.assertIn('BIND_DIRS="$TMPDIR"', script)
        self.assertIn("LITELLM_MASTER_KEY", script)
        self.assertIn("--enable-auto-tool-choice", script)
        self.assertIn("--tool-call-parser openai", script)
        self.assertIn('"${LITELLM_COMMAND}" --config "$LITELLM_CONFIG"', script)
        self.assertIn("Hosted provider egress preflight", script)
        self.assertIn("claude-snellius-local", full_config)
        self.assertIn("claude-snellius-hosted", full_config)
        self.assertIn("api_key: os.environ/SNELLIUS_HOSTED_API_KEY", full_config)
        self.assertNotIn("fallback", full_config.lower())
        self.assertIn("claude-snellius-local", local_only_config)
        self.assertNotIn("claude-snellius-hosted", local_only_config)
        self.assertEqual(result.data["gateway_url"], "http://localhost:4123")

    def test_litellm_config_does_not_inline_secrets_or_fallbacks(self) -> None:
        config = render_snellius_litellm_config(
            {
                "local_model_alias": "local",
                "served_model_name": "served-local",
                "hosted_model_alias": "hosted",
                "hosted_litellm_model": "openrouter/test-model",
                "hosted_api_key_env": "OPENROUTER_API_KEY",
            }
        )
        self.assertIn("model: openai/served-local", config)
        self.assertIn("model: openrouter/test-model", config)
        self.assertIn("api_key: os.environ/OPENROUTER_API_KEY", config)
        self.assertNotIn("sk-", config)
        self.assertNotIn("fallback", config.lower())

    def test_render_snellius_client_env_for_claude_code(self) -> None:
        text = render_snellius_client_env(
            {
                "snellius_user": "alice",
                "compute_node": "gcn31",
                "local_port": 4567,
                "gateway_port": 4000,
                "model_alias": "claude-snellius-hosted",
            }
        )
        self.assertIn("ssh -N -L 4567:gcn31:4000 alice@snellius.surf.nl", text)
        self.assertIn("ANTHROPIC_BASE_URL=http://localhost:4567", text)
        self.assertIn("ANTHROPIC_AUTH_TOKEN=${SNELLIUS_GATEWAY_TOKEN}", text)
        self.assertIn("ANTHROPIC_DEFAULT_SONNET_MODEL=claude-snellius-hosted", text)

    def test_router_prefers_enabled_snellius_for_heavy_tasks(self) -> None:
        config = AppConfig(
            config_dir=Path("configs"),
            run_mode=RunMode.FULL,
            models={
                "snellius_vllm": ModelConfig(
                    provider="vllm",
                    model="test/model",
                    host="http://localhost:8000/v1",
                    capabilities=["reasoning", "chemistry", "heavy", "long_context"],
                    enabled=True,
                ),
                "local_large": ModelConfig(
                    provider="ollama",
                    model="local/model",
                    host="http://localhost:11434",
                    capabilities=["reasoning", "chemistry"],
                    enabled=True,
                ),
            },
            model_routing=ModelRoutingConfig(default_alias="local_large", heavy_task_alias="snellius_vllm"),
        )
        selection = ModelRouter(config).select(
            {
                "task_type": "hypothesis_generation",
                "expected_difficulty": "high",
                "context_size": 64000,
                "privacy_required": False,
                "budget_mode": "full",
                "required_capabilities": ["reasoning"],
            }
        )
        self.assertEqual(selection.alias, "snellius_vllm")
        self.assertEqual(selection.provider, "vllm")

    def test_config_keeps_snellius_disabled_by_default(self) -> None:
        with patch.dict(os.environ, {"SNELLIUS_VLLM_ENABLED": "false"}, clear=False):
            config = load_config(Path("configs"), env_file=None, run_mode="cheap")
        self.assertIn("snellius_vllm", config.models)
        self.assertFalse(config.models["snellius_vllm"].enabled)

    def test_config_can_enable_snellius_from_environment(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SNELLIUS_VLLM_ENABLED": "true",
                "SNELLIUS_VLLM_MODEL": "test/model",
                "SNELLIUS_VLLM_BASE_URL": "http://localhost:8000/v1",
            },
            clear=False,
        ):
            config = load_config(Path("configs"), env_file=None, run_mode="full")
            self.assertEqual(config.models["snellius_vllm"].api_base, "http://localhost:8000/v1")
        self.assertTrue(config.models["snellius_vllm"].enabled)


if __name__ == "__main__":
    unittest.main()
