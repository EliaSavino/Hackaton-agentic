from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from hackathon_agents.config import ModelConfig, load_config
from hackathon_agents.llm.client import CompletionRequest, LLMClient


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(
            {
                "choices": [{"message": {"content": "openrouter response"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            }
        ).encode("utf-8")


class OpenRouterClientTests(unittest.TestCase):
    def test_default_config_contains_disabled_openrouter_alias(self) -> None:
        config = load_config("configs", run_mode="cheap")

        self.assertIn("openrouter_general", config.models)
        self.assertEqual(config.models["openrouter_general"].provider, "openrouter")
        self.assertFalse(config.models["openrouter_general"].enabled)

    def test_direct_openrouter_completion_uses_openai_compatible_request(self) -> None:
        captured = {}
        config = load_config("configs", run_mode="cheap")
        client = LLMClient(config)
        model = ModelConfig(
            provider="openrouter",
            model="openai/gpt-4o-mini",
            host="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            metadata={"http_referer": "https://example.test", "app_title": "Tests"},
        )

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _FakeResponse()

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                result = client._direct_openrouter_completion(
                    "openrouter_test",
                    model,
                    CompletionRequest(messages=[{"role": "user", "content": "Hello"}], max_tokens=12),
                )

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.content, "openrouter response")
        self.assertEqual(captured["url"], "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(captured["body"]["model"], "openai/gpt-4o-mini")
        self.assertEqual(captured["body"]["max_tokens"], 12)
        self.assertEqual(captured["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(captured["headers"]["Http-referer"], "https://example.test")
        self.assertEqual(captured["headers"]["X-openrouter-title"], "Tests")


if __name__ == "__main__":
    unittest.main()
