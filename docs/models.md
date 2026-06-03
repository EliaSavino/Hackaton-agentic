# Model Routing

The repo uses LiteLLM as the model gateway and `ModelRouter` as the local policy layer.

## Model Aliases

Model aliases are defined in `configs/models.yaml`. Agents ask for aliases or capabilities, not provider-specific details.

Example aliases:

- `frontier_reasoning`: high-quality hosted reasoning model.
- `science_reasoning`: hosted science-capable reasoning model.
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
