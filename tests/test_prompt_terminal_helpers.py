from __future__ import annotations

import unittest

from hackathon_agents.llm.prompt_terminal import (
    build_prompt_messages,
    build_user_prompt,
    terminal_metadata,
    trim_history,
)


class PromptTerminalHelperTests(unittest.TestCase):
    def test_build_user_prompt_without_rag_returns_prompt_unchanged(self) -> None:
        prompt = "Summarize the latest kinetic traces."

        self.assertEqual(build_user_prompt(prompt), prompt)
        self.assertEqual(build_user_prompt(prompt, rag_context=""), prompt)

    def test_build_user_prompt_wraps_trimmed_context(self) -> None:
        result = build_user_prompt("What is supported?", rag_context="  [1] Evidence text.  ")

        self.assertIn("<retrieved_context>\n[1] Evidence text.\n</retrieved_context>", result)
        self.assertIn("User prompt: What is supported?", result)
        self.assertIn("If the context is insufficient", result)

    def test_build_prompt_messages_orders_system_history_and_user_prompt(self) -> None:
        messages = build_prompt_messages(
            "Next step?",
            system_prompt="Stay grounded.",
            history=[
                {"role": "user", "content": "Prior question"},
                {"role": "assistant", "content": "Prior answer"},
            ],
        )

        self.assertEqual([message["role"] for message in messages], ["system", "user", "assistant", "user"])
        self.assertEqual(messages[-1]["content"], "Next step?")

    def test_build_prompt_messages_omits_absent_system_and_history(self) -> None:
        messages = build_prompt_messages("Hello")

        self.assertEqual(messages, [{"role": "user", "content": "Hello"}])

    def test_trim_history_returns_latest_messages(self) -> None:
        history = [{"role": "user", "content": str(index)} for index in range(5)]

        self.assertEqual(trim_history(history, max_messages=2), history[-2:])

    def test_trim_history_handles_zero_or_negative_limits(self) -> None:
        history = [{"role": "user", "content": "keep?"}]

        self.assertEqual(trim_history(history, max_messages=0), [])
        self.assertEqual(trim_history(history, max_messages=-1), [])

    def test_terminal_metadata_is_stable(self) -> None:
        metadata = terminal_metadata("openrouter_general", rag_enabled=True, rag_result_count=3)

        self.assertEqual(
            metadata,
            {
                "surface": "prompt_terminal",
                "model_alias": "openrouter_general",
                "rag_enabled": True,
                "rag_result_count": 3,
            },
        )


if __name__ == "__main__":
    unittest.main()
