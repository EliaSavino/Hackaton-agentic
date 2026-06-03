from __future__ import annotations

import ast
import io
import math
import multiprocessing as mp
import statistics
import traceback
from contextlib import redirect_stdout
from typing import Any

from pydantic import BaseModel, Field

from hackathon_agents.tools.base import error_result, ok_result


class PythonExecInput(BaseModel):
    code: str = Field(..., max_length=10_000)
    timeout_seconds: int = Field(default=5, ge=1, le=30)


_SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "pow": pow,
    "print": print,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


class _SafetyVisitor(ast.NodeVisitor):
    blocked_nodes = (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)
    blocked_names = {"__import__", "eval", "exec", "open", "compile", "input", "globals", "locals", "vars"}

    def visit(self, node: ast.AST) -> Any:
        if isinstance(node, self.blocked_nodes):
            raise ValueError(f"Blocked syntax: {type(node).__name__}")
        return super().visit(node)

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in self.blocked_names:
            raise ValueError(f"Blocked name: {node.id}")

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        if node.attr.startswith("__"):
            raise ValueError(f"Blocked dunder attribute: {node.attr}")
        self.generic_visit(node)


def _execute(code: str, queue: mp.Queue) -> None:
    stdout = io.StringIO()
    try:
        tree = ast.parse(code, mode="exec")
        _SafetyVisitor().visit(tree)
        compiled = compile(tree, "<hackathon_agents_snippet>", "exec")
        namespace: dict[str, Any] = {
            "__builtins__": _SAFE_BUILTINS,
            "math": math,
            "statistics": statistics,
        }
        with redirect_stdout(stdout):
            exec(compiled, namespace, namespace)
        public_vars = {
            key: value
            for key, value in namespace.items()
            if not key.startswith("_") and key not in {"math", "statistics"}
        }
        queue.put({"ok": True, "stdout": stdout.getvalue(), "variables": repr(public_vars)})
    except Exception as exc:
        queue.put({"ok": False, "error": str(exc), "traceback": traceback.format_exc(), "stdout": stdout.getvalue()})


def run_python(input_data: PythonExecInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, PythonExecInput) else PythonExecInput.model_validate(input_data)
    queue: mp.Queue = mp.Queue()
    process = mp.Process(target=_execute, args=(parsed.code, queue))
    process.start()
    process.join(parsed.timeout_seconds)

    if process.is_alive():
        process.terminate()
        process.join()
        return error_result("Python snippet timed out.", {"timeout_seconds": parsed.timeout_seconds})

    if queue.empty():
        return error_result("Python snippet exited without a result.")

    payload = queue.get()
    if payload.get("ok"):
        return ok_result(payload)
    return error_result(payload.get("error", "Python execution failed."), payload)
