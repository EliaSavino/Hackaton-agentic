# Configuration

Configuration is split into model, agent, and tool files.

```text
configs/
  models.yaml
  agents.yaml
  tools.yaml
```

Environment variables are loaded from `.env` when present.

## Run Modes

Supported run modes:

- `full`: prefer frontier models for final reasoning and difficult planning.
- `cheap`: prefer local Ollama models, reserve hosted models for final review.
- `offline`: only route to Ollama and local deterministic tools.
- `no_dft`: skip xTB and ORCA execution checks.

Set mode through `.env`:

```bash
HACKATHON_RUN_MODE=cheap
```

Or through CLI:

```bash
PYTHONPATH=src python -m hackathon_agents.cli demo "task" --run-mode offline
```

## Model Config

`configs/models.yaml` defines aliases.

Example:

```yaml
models:
  local_large:
    provider: ollama
    host: "http://${OLLAMA_BIG_HOST:-localhost}:11434"
    model: gpt-oss:latest
    capabilities: [reasoning, chemistry, local, private, cheap, bulk, offline]
    cost_tier: low
    enabled: true
```

Fields:

- `provider`: `openai`, `anthropic`, `ollama`, `hosted`, `vllm`, or `other`.
- `model`: provider model name.
- `host`: Ollama, hosted, or vLLM base URL when relevant.
- `capabilities`: labels used by `ModelRouter`.
- `api_key_env`: environment variable name for hosted API keys.
- `api_base_env`: optional hosted API base environment variable.
- `cost_tier`: `low`, `medium`, or `high`.
- `enabled`: disable without deleting config.

## Agent Config

`configs/agents.yaml` defines behavior and prompts.

Example:

```yaml
chemist:
  requires: [reasoning, chemistry]
  preferred_model: local_large
  fallback: [frontier_reasoning, science_reasoning]
  temperature: 0.3
  max_tokens: 1600
  system_prompt: |
    You are a cautious computational chemist.
    Generate chemically plausible candidate molecules with valid SMILES where possible.
```

Fields:

- `requires`: capabilities the agent needs.
- `preferred_model`: first alias to try when allowed.
- `fallback`: ordered fallback aliases.
- `temperature`: default sampling temperature.
- `max_tokens`: output budget.
- `system_prompt`: agent-level behavior instruction.

Keep prompts agent-specific rather than model-specific by default. Models should be swappable backends.

## Tool Config

`configs/tools.yaml` defines tool availability and executable settings.

Example:

```yaml
orca:
  enabled: true
  executable: orca
  timeout_seconds: 300
  enabled_modes: [full, offline]
```

Fields:

- `enabled`: whether the tool is usable.
- `executable`: command name for external tools.
- `timeout_seconds`: hard runtime cap.
- `enabled_modes`: run modes where the tool is active.

## Environment Variables

Common variables:

```bash
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
LITELLM_MODEL_DEFAULT=local_small
HACKATHON_RUN_MODE=cheap
OLLAMA_BIG_HOST=localhost
OLLAMA_SMALL_HOST=localhost
HOSTED_API_KEY=
HOSTED_API_BASE=
SNELLIUS_VLLM_ENABLED=false
SNELLIUS_VLLM_MODEL=
SNELLIUS_VLLM_BASE_URL=
```

Do not put API keys in YAML or source code.
