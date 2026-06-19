from __future__ import annotations

from typing import Any


def build_prompt_messages(
    prompt: str,
    *,
    system_prompt: str | None = None,
    history: list[dict[str, str]] | None = None,
    rag_context: str | None = None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history or [])
    messages.append({"role": "user", "content": build_user_prompt(prompt, rag_context=rag_context)})
    return messages


def build_user_prompt(prompt: str, *, rag_context: str | None = None) -> str:
    if not rag_context:
        return prompt
    return (
        "Use the retrieved context when it is relevant. If the context is insufficient, "
        "say what is missing instead of inventing evidence.\n\n"
        f"<retrieved_context>\n{rag_context.strip()}\n</retrieved_context>\n\n"
        f"User prompt: {prompt}"
    )


def trim_history(history: list[dict[str, str]], *, max_messages: int = 12) -> list[dict[str, str]]:
    if max_messages <= 0:
        return []
    return history[-max_messages:]


def terminal_metadata(model_alias: str | None, rag_enabled: bool, rag_result_count: int = 0) -> dict[str, Any]:
    return {
        "surface": "prompt_terminal",
        "model_alias": model_alias,
        "rag_enabled": rag_enabled,
        "rag_result_count": rag_result_count,
    }
