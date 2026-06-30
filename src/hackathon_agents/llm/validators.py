from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


_FENCE_RE = re.compile(r"^\s*```[ \t]*(?:[A-Za-z0-9_-]+)?[ \t]*\r?\n?(.*?)\s*```\s*$", re.DOTALL)
_FENCED_BLOCK_RE = re.compile(r"```[ \t]*(?:[A-Za-z0-9_-]+)?[ \t]*\r?\n?(.*?)\s*```", re.DOTALL)
_BEGIN_ENV_RE = re.compile(r"\\begin\{([^}]+)\}")
_END_ENV_RE = re.compile(r"\\end\{([^}]+)\}")


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    normalized: str
    errors: list[str]
    warnings: list[str] | None = None
    parsed: Any | None = None


def strip_markdown_fence(value: str) -> str:
    """Strip a single surrounding markdown fence from model output."""

    match = _FENCE_RE.match(value)
    if not match:
        return value.strip()
    return match.group(1).strip()


def validate_json_output(value: str) -> ValidationResult:
    normalized, warnings = normalize_json_output(value)
    try:
        parsed = json.loads(normalized)
    except Exception as exc:
        return ValidationResult(ok=False, normalized=normalized, errors=[str(exc)], warnings=warnings)
    return ValidationResult(ok=True, normalized=normalized, errors=[], warnings=warnings, parsed=parsed)


def validate_latex_output(value: str) -> ValidationResult:
    normalized = strip_markdown_fence(value)
    errors: list[str] = []
    warnings: list[str] = []
    if normalized != value.strip():
        warnings.append("stripped markdown fence")
    if "```" in normalized:
        errors.append("latex output contains markdown fences")
    environment_errors = _latex_environment_errors(normalized)
    errors.extend(environment_errors)
    if "\\section" not in normalized and "\\subsection" not in normalized and "\\paragraph" not in normalized:
        errors.append("latex output has no section-like structure")
    if "\\begin{document}" in normalized and "\\end{document}" not in normalized:
        errors.append("document environment is not closed")
    if "\\end{document}" in normalized and "\\begin{document}" not in normalized:
        errors.append("document environment is closed without being opened")
    if "\\begin{longtable}" in normalized and "\\usepackage{longtable}" not in normalized:
        warnings.append("longtable environment used without explicit longtable package")
    return ValidationResult(ok=not errors, normalized=normalized, errors=errors, warnings=warnings)


def normalize_json_output(value: str) -> tuple[str, list[str]]:
    """Normalize common model JSON wrappers and recover embedded JSON."""

    warnings: list[str] = []
    text = strip_markdown_fence(value)
    if text != value.strip():
        warnings.append("stripped markdown fence")
    try:
        json.loads(text)
        return text, warnings
    except Exception:
        pass

    fenced = _FENCED_BLOCK_RE.search(value)
    if fenced:
        candidate = fenced.group(1).strip()
        try:
            json.loads(candidate)
            warnings.append("extracted JSON from fenced block")
            return candidate, warnings
        except Exception:
            text = candidate

    extracted = _extract_json_candidate(text)
    if extracted != text:
        warnings.append("extracted embedded JSON object")
    return extracted, warnings


def _extract_json_candidate(text: str) -> str:
    starts = [index for index, character in enumerate(text) if character in "[{"]
    for start in starts:
        closing = "}" if text[start] == "{" else "]"
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            character = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    in_string = False
                continue
            if character == '"':
                in_string = True
                continue
            if character == text[start]:
                depth += 1
            elif character == closing:
                depth -= 1
                if depth == 0:
                    candidate = text[start : index + 1].strip()
                    try:
                        json.loads(candidate)
                    except Exception:
                        break
                    return candidate
    return text.strip()


def _latex_environment_errors(value: str) -> list[str]:
    errors: list[str] = []
    stack: list[str] = []
    tokens = [
        (match.start(), "begin", match.group(1))
        for match in _BEGIN_ENV_RE.finditer(value)
    ] + [
        (match.start(), "end", match.group(1))
        for match in _END_ENV_RE.finditer(value)
    ]
    for _, kind, environment in sorted(tokens):
        if kind == "begin":
            stack.append(environment)
            continue
        if not stack:
            errors.append(f"{environment} environment is closed without being opened")
            continue
        opened = stack.pop()
        if opened != environment:
            errors.append(f"{opened} environment closed by {environment}")
    for environment in reversed(stack):
        errors.append(f"{environment} environment is not closed")
    return errors
