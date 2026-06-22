from __future__ import annotations

import os
import re
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class RunMode(str, Enum):
    FULL = "full"
    NO_DFT = "no_dft"
    CHEAP = "cheap"
    OFFLINE = "offline"


class ModelConfig(BaseModel):
    provider: Literal["openai", "anthropic", "ollama", "hosted", "vllm", "openrouter", "other"]
    model: str
    host: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    api_key_env: str | None = None
    api_base_env: str | None = None
    cost_tier: Literal["low", "medium", "high"] = "medium"
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    @property
    def litellm_model(self) -> str:
        if self.provider == "ollama":
            return f"ollama/{self.model}"
        if self.provider == "vllm":
            return f"openai/{self.model}"
        if self.provider == "openrouter":
            if self.model.startswith("openrouter/"):
                return self.model
            return f"openrouter/{self.model}"
        return self.model

    @property
    def api_base(self) -> str | None:
        if self.provider == "ollama":
            return self.host
        if self.provider == "vllm":
            if self.api_base_env:
                return os.getenv(self.api_base_env)
            return self.host
        if self.provider == "openrouter":
            if self.api_base_env and os.getenv(self.api_base_env):
                return os.getenv(self.api_base_env)
            return self.host or "https://openrouter.ai/api/v1"
        if self.api_base_env:
            return os.getenv(self.api_base_env)
        return None

    @property
    def api_key(self) -> str | None:
        if not self.api_key_env:
            return None
        return os.getenv(self.api_key_env)


class AgentConfig(BaseModel):
    requires: list[str] = Field(default_factory=list)
    preferred_model: str | None = None
    fallback: list[str] = Field(default_factory=list)
    temperature: float = 0.1
    max_tokens: int = 1200
    system_prompt: str | None = None

    model_config = ConfigDict(extra="allow")


class ToolConfig(BaseModel):
    enabled: bool = True
    executable: str | None = None
    timeout_seconds: int | None = None
    enabled_modes: list[RunMode] | None = None
    allow_imports: bool | None = None
    jsonl_path: str | None = None
    markdown_path: str | None = None
    max_markdown_entries: int | None = None

    model_config = ConfigDict(extra="allow")

    def enabled_for_mode(self, run_mode: RunMode) -> bool:
        if not self.enabled:
            return False
        if self.enabled_modes is None:
            return True
        return run_mode in self.enabled_modes


class ModelRoutingConfig(BaseModel):
    default_alias: str = "local_small"
    cheap_final_review_alias: str | None = "frontier_reasoning"
    offline_required_provider: str = "ollama"
    heavy_task_alias: str | None = "snellius_vllm"

    model_config = ConfigDict(extra="allow")


class AppConfig(BaseModel):
    config_dir: Path
    run_mode: RunMode = RunMode.CHEAP
    models: dict[str, ModelConfig] = Field(default_factory=dict)
    agents: dict[str, AgentConfig] = Field(default_factory=dict)
    tools: dict[str, ToolConfig] = Field(default_factory=dict)
    model_routing: ModelRoutingConfig = Field(default_factory=ModelRoutingConfig)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def get_model(self, alias: str | None) -> ModelConfig:
        resolved = alias or self.model_routing.default_alias
        if resolved not in self.models:
            raise KeyError(f"Unknown model alias: {resolved}")
        return self.models[resolved]

    def get_agent(self, name: str) -> AgentConfig:
        if name not in self.agents:
            raise KeyError(f"Unknown agent config: {name}")
        return self.agents[name]

    def tool_enabled(self, name: str) -> bool:
        tool = self.tools.get(name)
        return bool(tool and tool.enabled_for_mode(self.run_mode))


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def _expand_env_string(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        braced_name, default, bare_name = match.groups()
        name = braced_name or bare_name
        return os.getenv(name, default or "")

    return _ENV_PATTERN.sub(replace, value)


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return _expand_env_string(value)
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value


def _load_env(env_file: Path) -> None:
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_file)
    except Exception:
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return _expand_env(data)


def load_config(
    config_dir: str | Path = "configs",
    env_file: str | Path | None = ".env",
    run_mode: str | RunMode | None = None,
) -> AppConfig:
    """Load YAML config and environment variables."""

    config_path = Path(config_dir)
    if env_file is not None:
        env_path = Path(env_file)
        if not env_path.is_absolute():
            env_path = config_path.parent / env_path
        _load_env(env_path)

    models_data = _load_yaml(config_path / "models.yaml")
    agents_data = _load_yaml(config_path / "agents.yaml")
    tools_data = _load_yaml(config_path / "tools.yaml")

    selected_run_mode = run_mode or os.getenv("HACKATHON_RUN_MODE") or RunMode.CHEAP.value
    mode = selected_run_mode if isinstance(selected_run_mode, RunMode) else RunMode(selected_run_mode)

    return AppConfig(
        config_dir=config_path,
        run_mode=mode,
        models=models_data.get("models", {}),
        agents=agents_data.get("agents", {}),
        tools=tools_data.get("tools", {}),
        model_routing=models_data.get("model_routing", {}),
    )
