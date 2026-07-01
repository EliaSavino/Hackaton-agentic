from __future__ import annotations

import shlex
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from hackathon_agents.tools.base import ok_result


class SnelliusVLLMJobInput(BaseModel):
    """Inputs for generating a Snellius SLURM job that serves vLLM."""

    output_dir: str | Path
    model_checkpoint: str
    container_path: str = "/projects/2/managed_datasets/containers/vllm/vllm.sif"
    project_space: str = ""
    download_dir: str = "$TMPDIR/vllm_downloads"
    job_name: str = "vllm_inference"
    partition: str = "gpu_a100"
    nodes: int = Field(default=1, ge=1)
    gpus_per_node: int = Field(default=1, ge=1, le=4)
    time_limit: str = "02:00:00"
    port: int = Field(default=8000, ge=1024, le=65535)
    uvicorn_log_level: str = "warning"
    extra_vllm_args: list[str] = Field(default_factory=list)
    filename: str = "run_vllm_serve.job"

    model_config = ConfigDict(extra="forbid")


class SnelliusLiteLLMConfigInput(BaseModel):
    """Inputs for rendering a LiteLLM gateway config for Claude Code."""

    local_model_alias: str = "claude-snellius-local"
    served_model_name: str = "claude-snellius-local"
    vllm_base_url: str = "http://127.0.0.1:8000/v1"
    vllm_api_key_env: str = "SNELLIUS_VLLM_API_KEY"
    hosted_model_alias: str = "claude-snellius-hosted"
    hosted_litellm_model: str = "anthropic/claude-sonnet-4-20250514"
    hosted_api_key_env: str = "SNELLIUS_HOSTED_API_KEY"
    include_hosted_alias: bool = True

    model_config = ConfigDict(extra="forbid")


class SnelliusGatewayJobInput(BaseModel):
    """Inputs for generating a Snellius SLURM job that serves vLLM behind LiteLLM."""

    output_dir: str | Path
    model_checkpoint: str
    served_model_name: str = "claude-snellius-local"
    local_model_alias: str = "claude-snellius-local"
    hosted_model_alias: str = "claude-snellius-hosted"
    hosted_litellm_model: str = "anthropic/claude-sonnet-4-20250514"
    hosted_api_key_env: str = "SNELLIUS_HOSTED_API_KEY"
    container_path: str = "/projects/2/managed_datasets/containers/vllm/vllm.sif"
    project_space: str = ""
    download_dir: str = "$TMPDIR/vllm_downloads"
    job_name: str = "snellius_llm_gateway"
    partition: str = "gpu_a100"
    nodes: int = Field(default=1, ge=1)
    gpus_per_node: int = Field(default=1, ge=1, le=4)
    time_limit: str = "02:00:00"
    vllm_host: str = "127.0.0.1"
    vllm_port: int = Field(default=8000, ge=1024, le=65535)
    gateway_host: str = "0.0.0.0"
    gateway_port: int = Field(default=4000, ge=1024, le=65535)
    local_client_port: int = Field(default=4000, ge=1024, le=65535)
    env_file: str = ".env"
    gateway_master_key_env: str = "SNELLIUS_GATEWAY_MASTER_KEY"
    vllm_api_key_env: str = "SNELLIUS_VLLM_API_KEY"
    litellm_command: str = "litellm"
    uvicorn_log_level: str = "warning"
    tool_call_parser: str = "openai"
    enable_auto_tool_choice: bool = True
    preflight_provider_egress: bool = True
    hosted_egress_url: str | None = None
    extra_vllm_args: list[str] = Field(default_factory=list)
    filename: str = "run_snellius_gateway.job"
    litellm_config_filename: str = "litellm_config.yaml"
    local_only_litellm_config_filename: str = "litellm_config.local_only.yaml"

    model_config = ConfigDict(extra="forbid")


class SnelliusClientEnvInput(BaseModel):
    """Inputs for rendering local Claude Code tunnel and environment commands."""

    snellius_user: str
    compute_node: str
    login_host: str = "snellius.surf.nl"
    local_port: int = Field(default=4000, ge=1024, le=65535)
    gateway_port: int = Field(default=4000, ge=1024, le=65535)
    model_alias: str = "claude-snellius-local"
    gateway_token_env: str = "SNELLIUS_GATEWAY_TOKEN"
    enable_model_discovery: bool = True

    model_config = ConfigDict(extra="forbid")


def generate_snellius_vllm_job(input_data: SnelliusVLLMJobInput | dict):
    """Generate a dry-run-safe SLURM script for Snellius vLLM serving."""

    parsed = (
        input_data
        if isinstance(input_data, SnelliusVLLMJobInput)
        else SnelliusVLLMJobInput.model_validate(input_data)
    )
    output_dir = Path(parsed.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    script_path = output_dir / parsed.filename
    script_path.write_text(render_snellius_vllm_job(parsed), encoding="utf-8")
    return ok_result(
        {
            "script_path": str(script_path),
            "base_url": f"http://localhost:{parsed.port}/v1",
            "model": parsed.model_checkpoint,
            "submit_hint": f"sbatch {script_path.name}",
            "tunnel_hint": (
                "After the job starts, expose the vLLM port with your Snellius SSH tunnel "
                f"and set SNELLIUS_VLLM_BASE_URL=http://localhost:{parsed.port}/v1."
            ),
        },
        artifacts=[str(script_path)],
    )


def generate_snellius_gateway_job(input_data: SnelliusGatewayJobInput | dict):
    """Generate a SLURM script plus LiteLLM configs for a Claude Code gateway."""

    parsed = (
        input_data
        if isinstance(input_data, SnelliusGatewayJobInput)
        else SnelliusGatewayJobInput.model_validate(input_data)
    )
    output_dir = Path(parsed.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    script_path = output_dir / parsed.filename
    full_config_path = output_dir / parsed.litellm_config_filename
    local_only_config_path = output_dir / parsed.local_only_litellm_config_filename

    config_input = {
        "local_model_alias": parsed.local_model_alias,
        "served_model_name": parsed.served_model_name,
        "vllm_base_url": f"http://{parsed.vllm_host}:{parsed.vllm_port}/v1",
        "vllm_api_key_env": parsed.vllm_api_key_env,
        "hosted_model_alias": parsed.hosted_model_alias,
        "hosted_litellm_model": parsed.hosted_litellm_model,
        "hosted_api_key_env": parsed.hosted_api_key_env,
    }

    script_path.write_text(render_snellius_gateway_job(parsed), encoding="utf-8")
    full_config_path.write_text(
        render_snellius_litellm_config({**config_input, "include_hosted_alias": True}),
        encoding="utf-8",
    )
    local_only_config_path.write_text(
        render_snellius_litellm_config({**config_input, "include_hosted_alias": False}),
        encoding="utf-8",
    )

    return ok_result(
        {
            "script_path": str(script_path),
            "litellm_config_path": str(full_config_path),
            "local_only_litellm_config_path": str(local_only_config_path),
            "gateway_url": f"http://localhost:{parsed.local_client_port}",
            "local_model_alias": parsed.local_model_alias,
            "hosted_model_alias": parsed.hosted_model_alias,
            "submit_hint": f"sbatch {script_path.name}",
            "tunnel_hint": (
                "After the job starts, tunnel the reported compute node gateway port, for example: "
                f"ssh -N -L {parsed.local_client_port}:<compute-node>:{parsed.gateway_port} "
                "<user>@snellius.surf.nl"
            ),
            "env_hint": (
                f"Set ANTHROPIC_BASE_URL=http://localhost:{parsed.local_client_port}, "
                "ANTHROPIC_AUTH_TOKEN to your LiteLLM gateway token, and "
                f"ANTHROPIC_DEFAULT_SONNET_MODEL={parsed.local_model_alias}."
            ),
        },
        artifacts=[str(script_path), str(full_config_path), str(local_only_config_path)],
    )


def render_snellius_litellm_config(input_data: SnelliusLiteLLMConfigInput | dict) -> str:
    """Render a LiteLLM config without embedding provider secrets."""

    parsed = (
        input_data
        if isinstance(input_data, SnelliusLiteLLMConfigInput)
        else SnelliusLiteLLMConfigInput.model_validate(input_data)
    )
    lines = [
        "model_list:",
        f"  - model_name: {parsed.local_model_alias}",
        "    litellm_params:",
        f"      model: openai/{parsed.served_model_name}",
        f"      api_base: {parsed.vllm_base_url.rstrip('/')}",
        f"      api_key: os.environ/{parsed.vllm_api_key_env}",
    ]
    if parsed.include_hosted_alias:
        lines.extend(
            [
                f"  - model_name: {parsed.hosted_model_alias}",
                "    litellm_params:",
                f"      model: {parsed.hosted_litellm_model}",
                f"      api_key: os.environ/{parsed.hosted_api_key_env}",
            ]
        )
    lines.extend(
        [
            "litellm_settings:",
            "  drop_params: true",
            "  set_verbose: false",
        ]
    )
    return "\n".join(lines) + "\n"


def render_snellius_client_env(input_data: SnelliusClientEnvInput | dict) -> str:
    """Render local tunnel and Claude Code environment commands."""

    parsed = (
        input_data
        if isinstance(input_data, SnelliusClientEnvInput)
        else SnelliusClientEnvInput.model_validate(input_data)
    )
    token_ref = f"${{{parsed.gateway_token_env}}}"
    lines = [
        "# Start this tunnel from your local workstation:",
        (
            f"ssh -N -L {parsed.local_port}:{parsed.compute_node}:{parsed.gateway_port} "
            f"{parsed.snellius_user}@{parsed.login_host}"
        ),
        "",
        "# In the shell where you launch Claude Code:",
        f"export ANTHROPIC_BASE_URL=http://localhost:{parsed.local_port}",
        f"export ANTHROPIC_AUTH_TOKEN={token_ref}",
        f"export ANTHROPIC_API_KEY={token_ref}",
        f"export ANTHROPIC_DEFAULT_OPUS_MODEL={parsed.model_alias}",
        f"export ANTHROPIC_DEFAULT_SONNET_MODEL={parsed.model_alias}",
        f"export ANTHROPIC_DEFAULT_HAIKU_MODEL={parsed.model_alias}",
    ]
    if parsed.enable_model_discovery:
        lines.append("export CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1")
    lines.extend(["", "claude"])
    return "\n".join(lines) + "\n"


def render_snellius_vllm_job(input_data: SnelliusVLLMJobInput | dict) -> str:
    """Render the SLURM script text without writing it."""

    parsed = (
        input_data
        if isinstance(input_data, SnelliusVLLMJobInput)
        else SnelliusVLLMJobInput.model_validate(input_data)
    )
    bind_dirs = '"$TMPDIR"'
    if parsed.project_space:
        bind_dirs = f'"$TMPDIR",{parsed.project_space}'
    extra_args = " ".join(parsed.extra_vllm_args)
    extra_args_suffix = f" {extra_args}" if extra_args else ""
    return "\n".join(
        [
            "#!/bin/bash",
            f"#SBATCH --job-name={parsed.job_name}",
            f"#SBATCH --partition={parsed.partition}",
            f"#SBATCH --nodes={parsed.nodes}",
            "#SBATCH --ntasks=1",
            f"#SBATCH --gpus-per-node={parsed.gpus_per_node}",
            f"#SBATCH --time={parsed.time_limit}",
            "",
            "set -euo pipefail",
            "",
            f"CONTAINER_PATH={parsed.container_path}",
            f"MODEL_CHECKPOINT={parsed.model_checkpoint}",
            f"PORT={parsed.port}",
            f"DOWNLOAD_DIR={parsed.download_dir}",
            f"BIND_DIRS={bind_dirs}",
            "",
            "mkdir -p \"$DOWNLOAD_DIR\"",
            "echo \"Starting vLLM server on port $PORT for $MODEL_CHECKPOINT\"",
            "echo \"OpenAI-compatible base URL inside the job: http://localhost:$PORT/v1\"",
            "",
            "apptainer exec --nv \\",
            "  -B \"${BIND_DIRS}\" \\",
            "  \"${CONTAINER_PATH}\" \\",
            "  vllm serve \"${MODEL_CHECKPOINT}\" \\",
            "  --tensor-parallel-size \"${SLURM_GPUS_ON_NODE:-1}\" \\",
            "  --download-dir \"${DOWNLOAD_DIR}\" \\",
            f"  --uvicorn-log-level {parsed.uvicorn_log_level} \\",
            f"  --port \"${{PORT}}\"{extra_args_suffix}",
            "",
        ]
    )


def render_snellius_gateway_job(input_data: SnelliusGatewayJobInput | dict) -> str:
    """Render a SLURM script that runs vLLM behind an authenticated LiteLLM proxy."""

    parsed = (
        input_data
        if isinstance(input_data, SnelliusGatewayJobInput)
        else SnelliusGatewayJobInput.model_validate(input_data)
    )
    bind_dirs = "$TMPDIR"
    if parsed.project_space:
        bind_dirs = f"$TMPDIR,{parsed.project_space}"
    extra_args = " ".join(shlex.quote(arg) for arg in parsed.extra_vllm_args)
    extra_args_array = f"EXTRA_VLLM_ARGS=({extra_args})" if extra_args else "EXTRA_VLLM_ARGS=()"
    tool_choice_args = ["TOOL_ARGS=()"]
    if parsed.enable_auto_tool_choice:
        tool_choice_args.append("TOOL_ARGS+=(--enable-auto-tool-choice)")
    if parsed.tool_call_parser:
        tool_choice_args.append(f"TOOL_ARGS+=(--tool-call-parser {_q(parsed.tool_call_parser)})")
    hosted_egress_url = parsed.hosted_egress_url or _default_hosted_egress_url(parsed.hosted_litellm_model)
    preflight = "true" if parsed.preflight_provider_egress else "false"

    return "\n".join(
        [
            "#!/bin/bash",
            f"#SBATCH --job-name={parsed.job_name}",
            f"#SBATCH --partition={parsed.partition}",
            f"#SBATCH --nodes={parsed.nodes}",
            "#SBATCH --ntasks=1",
            f"#SBATCH --gpus-per-node={parsed.gpus_per_node}",
            f"#SBATCH --time={parsed.time_limit}",
            "",
            "set -euo pipefail",
            "",
            'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
            f"ENV_FILE=${{SNELLIUS_ENV_FILE:-{_q(parsed.env_file)}}}",
            'if [[ "$ENV_FILE" != /* ]]; then',
            '  ENV_FILE="${SCRIPT_DIR}/${ENV_FILE}"',
            "fi",
            f"CONTAINER_PATH={_q(parsed.container_path)}",
            f"MODEL_CHECKPOINT={_q(parsed.model_checkpoint)}",
            f"SERVED_MODEL_NAME={_q(parsed.served_model_name)}",
            f"VLLM_HOST={_q(parsed.vllm_host)}",
            f"VLLM_PORT={parsed.vllm_port}",
            f"GATEWAY_HOST={_q(parsed.gateway_host)}",
            f"GATEWAY_PORT={parsed.gateway_port}",
            f"DOWNLOAD_DIR={_q_allow_env(parsed.download_dir)}",
            f"BIND_DIRS={_q_allow_env(bind_dirs)}",
            f"LITELLM_COMMAND={_q(parsed.litellm_command)}",
            f"LITELLM_CONFIG_FULL=\"${{SCRIPT_DIR}}/{parsed.litellm_config_filename}\"",
            f"LITELLM_CONFIG_LOCAL_ONLY=\"${{SCRIPT_DIR}}/{parsed.local_only_litellm_config_filename}\"",
            f"GATEWAY_MASTER_KEY_ENV={_q(parsed.gateway_master_key_env)}",
            f"VLLM_API_KEY_ENV={_q(parsed.vllm_api_key_env)}",
            f"HOSTED_API_KEY_ENV={_q(parsed.hosted_api_key_env)}",
            f"HOSTED_LITELLM_MODEL={_q(parsed.hosted_litellm_model)}",
            f"HOSTED_EGRESS_URL={_q(hosted_egress_url)}",
            f"PREFLIGHT_PROVIDER_EGRESS={preflight}",
            f"UVICORN_LOG_LEVEL={_q(parsed.uvicorn_log_level)}",
            extra_args_array,
            *tool_choice_args,
            "",
            "load_env_file() {",
            '  if [ -f "$ENV_FILE" ]; then',
            '    env_mode="$(stat -c "%a" "$ENV_FILE" 2>/dev/null || true)"',
            '    if [ -n "$env_mode" ] && [ "$env_mode" != "600" ]; then',
            '      echo "Warning: $ENV_FILE permissions are $env_mode; run chmod 600 $ENV_FILE."',
            "    fi",
            "    set -a",
            '    . "$ENV_FILE"',
            "    set +a",
            "  else",
            '    echo "Warning: $ENV_FILE not found. Provider keys and gateway token must already be exported."',
            "  fi",
            "}",
            "",
            "require_var() {",
            '  local name="$1"',
            '  if [ -z "${!name:-}" ]; then',
            '    echo "Required environment variable $name is not set."',
            "    return 1",
            "  fi",
            "}",
            "",
            "require_command() {",
            '  local command_name="$1"',
            '  if ! command -v "$command_name" >/dev/null 2>&1; then',
            '    echo "Required command not found on PATH: $command_name"',
            "    return 1",
            "  fi",
            "}",
            "",
            "derive_hosted_key() {",
            '  if [ -n "${!HOSTED_API_KEY_ENV:-}" ]; then',
            "    return 0",
            "  fi",
            '  case "$HOSTED_LITELLM_MODEL" in',
            '    anthropic/*|claude*) export "${HOSTED_API_KEY_ENV}=${ANTHROPIC_API_KEY:-}" ;;',
            '    openai/*|gpt-*) export "${HOSTED_API_KEY_ENV}=${OPENAI_API_KEY:-}" ;;',
            '    openrouter/*) export "${HOSTED_API_KEY_ENV}=${OPENROUTER_API_KEY:-}" ;;',
            "  esac",
            "}",
            "",
            "wait_for_http() {",
            '  local url="$1"',
            '  local name="$2"',
            "  for _ in $(seq 1 120); do",
            '    if curl -sS --connect-timeout 2 --max-time 5 -o /dev/null "$url"; then',
            '      echo "$name is reachable at $url"',
            "      return 0",
            "    fi",
            "    sleep 2",
            "  done",
            '  echo "$name did not become reachable at $url"',
            "  return 1",
            "}",
            "",
            "load_env_file",
            "require_command curl",
            'require_command "$LITELLM_COMMAND"',
            'require_var "$GATEWAY_MASTER_KEY_ENV"',
            'export LITELLM_MASTER_KEY="${!GATEWAY_MASTER_KEY_ENV}"',
            'if [ -z "${!VLLM_API_KEY_ENV:-}" ]; then',
            '  export "${VLLM_API_KEY_ENV}=EMPTY"',
            "fi",
            "derive_hosted_key",
            "",
            "HOSTED_ALIAS_ENABLED=${SNELLIUS_HOSTED_ALIAS_ENABLED:-true}",
            'if [ "$HOSTED_ALIAS_ENABLED" = "true" ]; then',
            '  if [ -z "${!HOSTED_API_KEY_ENV:-}" ]; then',
            '    echo "Hosted alias disabled: $HOSTED_API_KEY_ENV is not set and no provider key was derivable."',
            "    HOSTED_ALIAS_ENABLED=false",
            '  elif [ "$PREFLIGHT_PROVIDER_EGRESS" = "true" ]; then',
            '    if curl -sS --connect-timeout 5 --max-time 10 -o /dev/null "$HOSTED_EGRESS_URL"; then',
            '      echo "Hosted provider egress preflight succeeded: $HOSTED_EGRESS_URL"',
            "    else",
            '      echo "Hosted alias disabled: provider egress preflight failed for $HOSTED_EGRESS_URL."',
            "      HOSTED_ALIAS_ENABLED=false",
            "    fi",
            "  fi",
            "fi",
            "",
            'if [ "$HOSTED_ALIAS_ENABLED" = "true" ]; then',
            '  LITELLM_CONFIG="$LITELLM_CONFIG_FULL"',
            "else",
            '  LITELLM_CONFIG="$LITELLM_CONFIG_LOCAL_ONLY"',
            "fi",
            "",
            "mkdir -p \"$DOWNLOAD_DIR\"",
            "echo \"Starting vLLM on ${VLLM_HOST}:${VLLM_PORT} for $MODEL_CHECKPOINT as $SERVED_MODEL_NAME\"",
            "VLLM_COMMAND=(",
            "  apptainer exec --nv",
            "  -B \"${BIND_DIRS}\"",
            "  \"${CONTAINER_PATH}\"",
            "  vllm serve \"${MODEL_CHECKPOINT}\"",
            "  --host \"${VLLM_HOST}\"",
            "  --port \"${VLLM_PORT}\"",
            "  --served-model-name \"${SERVED_MODEL_NAME}\"",
            "  --tensor-parallel-size \"${SLURM_GPUS_ON_NODE:-1}\"",
            "  --download-dir \"${DOWNLOAD_DIR}\"",
            "  --uvicorn-log-level \"${UVICORN_LOG_LEVEL}\"",
            ")",
            'VLLM_COMMAND+=("${TOOL_ARGS[@]}" "${EXTRA_VLLM_ARGS[@]}")',
            '"${VLLM_COMMAND[@]}" &',
            "VLLM_PID=$!",
            "",
            "trap 'kill ${GATEWAY_PID:-} ${VLLM_PID:-} 2>/dev/null || true' EXIT",
            "wait_for_http \"http://${VLLM_HOST}:${VLLM_PORT}/v1/models\" vLLM",
            "",
            "echo \"Starting LiteLLM gateway on ${GATEWAY_HOST}:${GATEWAY_PORT} with $LITELLM_CONFIG\"",
            '"${LITELLM_COMMAND}" --config "$LITELLM_CONFIG" --host "$GATEWAY_HOST" --port "$GATEWAY_PORT" &',
            "GATEWAY_PID=$!",
            "wait_for_http \"http://127.0.0.1:${GATEWAY_PORT}/health\" LiteLLM",
            "",
            "echo \"Gateway ready.\"",
            "echo \"From your workstation, tunnel with:\"",
            "echo \"ssh -N -L ${GATEWAY_PORT}:${SLURMD_NODENAME:-$(hostname)}:${GATEWAY_PORT} <user>@snellius.surf.nl\"",
            "echo \"Then set ANTHROPIC_BASE_URL=http://localhost:${GATEWAY_PORT} for Claude Code.\"",
            "",
            "wait \"$GATEWAY_PID\"",
            "",
        ]
    )


def _default_hosted_egress_url(model: str) -> str:
    if model.startswith("openai/") or model.startswith("gpt-"):
        return "https://api.openai.com/v1/models"
    if model.startswith("openrouter/"):
        return "https://openrouter.ai/api/v1/models"
    return "https://api.anthropic.com"


def _q(value: str) -> str:
    return shlex.quote(value)


def _q_allow_env(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$(", "\\$(")
    )
    return f'"{escaped}"'
