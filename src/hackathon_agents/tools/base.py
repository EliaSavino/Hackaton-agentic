from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from hackathon_agents.schemas.results import ToolResult

InputT = TypeVar("InputT", bound=BaseModel)


class BaseTool(ABC, Generic[InputT]):
    name: str

    @abstractmethod
    def run(self, tool_input: InputT) -> ToolResult:
        raise NotImplementedError


def ok_result(data: dict[str, Any] | None = None, artifacts: list[str] | None = None) -> ToolResult:
    return ToolResult(ok=True, data=data or {}, artifacts=artifacts or [])


def error_result(error: str, data: dict[str, Any] | None = None, artifacts: list[str] | None = None) -> ToolResult:
    return ToolResult(ok=False, data=data or {}, error=error, artifacts=artifacts or [])
