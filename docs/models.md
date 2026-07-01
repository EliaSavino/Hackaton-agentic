# Model Routing

The repo uses LiteLLM as the model gateway and `ModelRouter` as the local policy layer.

## Model Aliases

Model aliases are defined in `configs/models.yaml`. Agents ask for aliases or capabilities, not provider-specific details.

Example aliases:

- `frontier_reasoning`: high-quality hosted reasoning model.
- `science_reasoning`: hosted science-capable reasoning model.
- `openrouter_general`: disabled-by-default OpenRouter alias for the OpenAI-compatible OpenRouter gateway.
- `snellius_vllm`: disabled-by-default OpenAI-compatible vLLM endpoint for heavyweight Snellius inference.
- `local_large`: larger Ollama model for local reasoning, privacy, and bulk work.
- `local_small`: smaller Ollama model for routing, summarization, formatting, and cheap tasks.

## Router Inputs

`ModelRouter.select()` accepts:

- `task_type`
- `expected_difficulty`
- `context_size`
- `privacy_required`
- `budget_mode`
- `required_capabilities`
- `agent_name`

The output is a selected backend alias.

## Routing Policy

Practical default behavior:

- `offline`: only Ollama providers are allowed.
- `privacy_required`: only local Ollama providers are allowed.
- `cheap`: favor `local_large` or `local_small`; allow frontier review for final criticism.
- `full`: prefer hosted frontier models for difficult planning and final reasoning; use local models for bulk hypotheses.
- high-difficulty or large-context requests prefer `model_routing.heavy_task_alias` when it is enabled and reachable.

## Snellius vLLM

SURF's Snellius vLLM setup serves models through an OpenAI-compatible HTTP API after a SLURM job starts the vLLM server. The repo models this as:

```yaml
snellius_vllm:
  provider: vllm
  model: "${SNELLIUS_VLLM_MODEL:-meta-llama/Llama-3.1-70B-Instruct}"
  api_base_env: SNELLIUS_VLLM_BASE_URL
  enabled: "${SNELLIUS_VLLM_ENABLED:-false}"
```

The endpoint should include `/v1`, for example:

```bash
SNELLIUS_VLLM_BASE_URL=http://localhost:8000/v1
```

Use the helper command to generate a SLURM script:

```bash
PYTHONPATH=src python -m hackathon_agents.cli snellius-vllm-script \
  --model-checkpoint meta-llama/Llama-3.1-70B-Instruct \
  --output-dir runs/snellius_vllm
```

Submit that script on Snellius, expose or tunnel the vLLM port, then run `check-models`. API keys are optional for vLLM unless a config sets `metadata.requires_api_key: true`.

## Snellius Claude Code Gateway

For Claude Code users, prefer the combined LiteLLM gateway instead of exposing vLLM directly. It keeps vLLM bound to `127.0.0.1` inside the SLURM job and exposes LiteLLM as the authenticated Anthropic-compatible gateway.

Generate the job and configs:

```bash
PYTHONPATH=src python -m hackathon_agents.cli snellius-gateway-script \
  --model-checkpoint openai/gpt-oss-120b \
  --output-dir runs/snellius_gateway \
  --served-model-name claude-snellius-local \
  --gateway-port 4000
```

The generator writes:

- `run_snellius_gateway.job`: starts vLLM and LiteLLM.
- `litellm_config.yaml`: exposes `claude-snellius-local` and `claude-snellius-hosted`.
- `litellm_config.local_only.yaml`: exposes only `claude-snellius-local`.

Keep provider keys and the gateway token in the Snellius `.env`, not in generated YAML:

```bash
SNELLIUS_GATEWAY_MASTER_KEY=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
OPENROUTER_API_KEY=
SNELLIUS_HOSTED_API_KEY=
SNELLIUS_HOSTED_ALIAS_ENABLED=true
```

Run `chmod 600 .env` before submitting the job. At startup, the script checks that a gateway token exists, derives `SNELLIUS_HOSTED_API_KEY` from the provider-specific key when possible, and disables the hosted alias if the key or provider egress preflight fails.

After the job starts and reports a compute node, generate local Claude Code commands:

```bash
PYTHONPATH=src python -m hackathon_agents.cli snellius-client-env \
  --snellius-user "$USER" \
  --compute-node gcn31 \
  --model-alias claude-snellius-local
```

This prints an SSH tunnel command plus `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY`, and `ANTHROPIC_DEFAULT_*_MODEL` exports. Users without Snellius SSH accounts are not automated in v1; they need an approved SURF/OOD/front-door access path.

## OpenRouter

OpenRouter is configured as an OpenAI-compatible hosted provider:

```yaml
openrouter_general:
  provider: openrouter
  model: "${OPENROUTER_MODEL:-~openai/gpt-latest}"
  host: "${OPENROUTER_API_BASE:-https://openrouter.ai/api/v1}"
  api_key_env: OPENROUTER_API_KEY
  enabled: "${OPENROUTER_ENABLED:-false}"
```

Enable it with:

```bash
OPENROUTER_ENABLED=true
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=~openai/gpt-latest
OPENROUTER_APP_TITLE="Hackathon Agents"
```

`LLMClient` first attempts LiteLLM. If LiteLLM is unavailable or the provider call fails, OpenRouter uses a direct `/chat/completions` fallback against the configured `/api/v1` base URL. `check-models` calls the OpenAI-compatible `/models` endpoint when the API key is present.

## Good Local Tasks

Use local models for:

- bulk molecule ideation
- summarization
- simple routing
- formatting
- information extraction
- privacy-sensitive context
- many cheap hypotheses

## Good Frontier Tasks

Use frontier models for:

- final scientific critique
- experimental design decisions
- complex debugging
- checking conclusions
- resolving contradictory evidence

## Health Checks

Run:

```bash
PYTHONPATH=src python -m hackathon_agents.cli check-models
```

For Ollama, this calls `/api/tags` and checks whether configured models are listed.
For vLLM and OpenRouter, this calls the OpenAI-compatible `/v1/models` endpoint.

## Benchmarking

Run:

```bash
PYTHONPATH=src python -m hackathon_agents.cli benchmark-models
```

The benchmark tests:

- latency
- tool-call style output
- JSON compliance
- simple chemistry reasoning
- code generation

Results are saved to `runs/model_benchmark_<date>.json`.

## Calling A Model From An Agent

Recommended pattern:

```python
from hackathon_agents.llm.client import CompletionRequest, LLMClient
from hackathon_agents.llm.router import ModelRouter

agent_config = config.get_agent("chemist")
selection = ModelRouter(config).select_for_agent("chemist")

messages = [
    {"role": "system", "content": agent_config.system_prompt or ""},
    {"role": "user", "content": "Generate 5 molecule ideas as JSON."},
]

result = LLMClient(config).complete(
    CompletionRequest(
        model_alias=selection.alias,
        messages=messages,
        temperature=agent_config.temperature,
        max_tokens=agent_config.max_tokens,
        fallback_aliases=agent_config.fallback,
    )
)
```

Validate `result.content` before putting it into state.
