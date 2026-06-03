# hackathon-agents

A robust scaffold for chem/bio scientific-discovery agents. The design favors clean interfaces, typed tools, config-driven agents, logging, and testability over a flashy demo.

## Documentation

Detailed docs live in [docs/README.md](docs/README.md).

Start with:

- [Quickstart](docs/quickstart.md)
- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Model Routing](docs/models.md)
- [Agents](docs/agents.md)
- [Graph And Iteration](docs/graph-iteration.md)
- [Tools](docs/tools.md)
- [Paper Review](docs/paper-review.md)
- [Testing](docs/testing.md)
- [Hackathon Playbook](docs/hackathon-playbook.md)

## Setup

```bash
uv sync
cp .env.example .env
```

Conda:

```bash
conda env create -f environment.yml
conda activate hackathon-agents
cp .env.example .env
```

Poetry also works:

```bash
poetry install
cp .env.example .env
```

Required environment variables:

```bash
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
LITELLM_MODEL_DEFAULT=local_small
```

Useful local model variables:

```bash
OLLAMA_BIG_HOST=localhost
OLLAMA_SMALL_HOST=localhost
HACKATHON_RUN_MODE=cheap
```

The code supports four run modes:

- `full`: prefer frontier models for final reasoning, use local models for bulk work.
- `no_dft`: skip xTB and ORCA execution.
- `cheap`: favor local Ollama models and reserve frontier calls for final criticism.
- `offline`: only route to Ollama models and local tools.

## Run the Demo

```bash
python -m hackathon_agents.cli demo "Find promising substrate candidates for reaction X"
```

Outputs are written to `runs/<timestamp>/`:

- `report.docx`
- `state.json`
- any generated plots or DFT input files

## Benchmark Models

```bash
python -m hackathon_agents.cli benchmark-models
```

This pings configured Ollama hosts, tests configured models on latency, JSON compliance, tool-call formatting, simple chemistry reasoning, and code generation, then saves results to `runs/model_benchmark_<date>.json`.

## Review A Paper

```bash
python -m hackathon_agents.cli review-paper path/to/paper.txt \
  --domain chem_bio \
  --focus-question "Are controls and replicates described?"
```

Supported inputs are `.txt`, `.md`, `.pdf`, and `.docx`. PDF extraction uses `pypdf`; DOCX extraction uses `python-docx`. The output is a structured JSON review with metadata, detected sections, claim-like statements, strengths, limitations, reproducibility checklist items, focus-question evidence, and a deterministic recommendation.

## Architecture

The graph is deterministic:

```text
user request -> planner -> chemist -> tool execution -> critic -> writer -> final output
```

The default implementation also supports a bounded iterative loop:

```text
planner
  -> chemist
  -> tool execution
  -> critic
      -> chemist if needs_more_passes and iteration < max_iterations
      -> writer otherwise
```

Agents are thin. They interpret config and update state. Tools do deterministic work and return `ToolResult`:

```python
ToolResult(ok=True, data={}, error=None, artifacts=[])
```

Errors are accumulated in state rather than crashing the whole run.

## Model Routing

Models live in `configs/models.yaml`. Agents request capabilities in `configs/agents.yaml`, while `ModelRouter` maps those requests to OpenAI, Anthropic, hosted APIs, or Ollama servers.

The rest of the code works with model aliases and does not know which backend is selected.

Good local-model tasks:

- molecule ideation
- paper summarization
- text cleanup and extraction
- many parallel hypotheses

Good frontier-model tasks:

- final scientific reasoning
- debugging
- experimental design decisions
- checking conclusions

For cheap local fanout, `hackathon_agents.agents.chemist.generate_parallel_hypotheses()` provides a bounded aggregation hook. It defaults to deterministic seed generation, and teams can replace the worker body with local Ollama calls while keeping frontier criticism as the final ranking step.

## Iterating Agent Passes

The loop is controlled by typed state in `src/hackathon_agents/state.py`:

- `iteration`
- `max_iterations`
- `needs_more_passes`
- `requested_next_actions`
- `stop_reason`
- `critic_decisions`

The critic is responsible for recommending another pass. The graph is responsible for enforcing the hard cap.

Useful demo knobs:

```bash
python -m hackathon_agents.cli demo \
  "Find promising substrate candidates for reaction X" \
  --max-iterations 3 \
  --min-valid-candidates 10 \
  --score-threshold 0.75
```

Good loop criteria are intentionally simple:

- generate another pass if valid candidates are below target
- generate another pass if the best score is below threshold and still improving
- stop at `max_iterations`
- stop when deterministic tools are unavailable
- stop when too many tool errors accumulate
- stop when there is no material score improvement

Agent system prompts live in `configs/agents.yaml`. Model definitions live in `configs/models.yaml`. The same agent prompt can be routed to OpenAI, Anthropic, hosted APIs, or local Ollama by changing model aliases and capabilities.

## Add a New Agent

1. Add a config entry in `configs/agents.yaml`.
2. Create `src/hackathon_agents/agents/<name>.py`.
3. Keep the agent thin: read state, optionally ask the model gateway, and update state.
4. Wire the node into `src/hackathon_agents/graph.py` if it belongs in the deterministic workflow.

## Add a New Tool

1. Create a typed input/output wrapper in `src/hackathon_agents/tools/`.
2. Return `ToolResult` for every path, including errors.
3. Add tool settings to `configs/tools.yaml`.
4. Add a focused smoke test in `tests/`.

## Hackathon Checklist

- Confirm `.env` has the right hosted API keys.
- Start both Ollama servers if working offline or cheap.
- Run `python -m hackathon_agents.cli benchmark-models`.
- Run `python -m unittest discover -s tests`.
- Use `no_dft` mode if xTB or ORCA are not installed.
- Keep tool execution deterministic and bounded.
- Save every run artifact under `runs/`.
