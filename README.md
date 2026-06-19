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

Useful OpenRouter variables:

```bash
OPENROUTER_ENABLED=true
OPENROUTER_API_KEY=
OPENROUTER_MODEL=~openai/gpt-latest
OPENROUTER_HTTP_REFERER=
OPENROUTER_APP_TITLE=Hackathon Agents
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

## Local RAG And Prompt Terminal

Index local documents into the SQLite RAG database:

```bash
python -m hackathon_agents.cli rag-ingest docs --db-path data/rag.sqlite
```

Search indexed context:

```bash
python -m hackathon_agents.cli rag-search "photoredox light intensity" --context
```

Open an interactive prompting terminal with per-prompt RAG retrieval:

```bash
python -m hackathon_agents.cli prompt-terminal \
  --model-alias openrouter_general \
  --db-path data/rag.sqlite
```

Use `--no-rag` for plain chat, `/rag <query>` to inspect retrieved context, `/clear` to clear recent history, and `/exit` to leave the terminal.

## Snellius vLLM For Heavy Tasks

The model router can send high-difficulty or large-context requests to a Snellius-hosted vLLM server through the disabled-by-default `snellius_vllm` alias in `configs/models.yaml`.

Generate a Snellius SLURM script:

```bash
python -m hackathon_agents.cli snellius-vllm-script \
  --model-checkpoint meta-llama/Llama-3.1-70B-Instruct \
  --output-dir runs/snellius_vllm \
  --partition gpu_a100 \
  --gpus-per-node 1 \
  --port 8000
```

Copy or create the script on Snellius, submit it with `sbatch`, then expose the vLLM OpenAI-compatible endpoint to your local machine. Once the endpoint is reachable, set:

```bash
SNELLIUS_VLLM_ENABLED=true
SNELLIUS_VLLM_MODEL=meta-llama/Llama-3.1-70B-Instruct
SNELLIUS_VLLM_BASE_URL=http://localhost:8000/v1
```

Then check availability:

```bash
python -m hackathon_agents.cli check-models
```

When enabled and reachable, high-difficulty or large-context routing requests prefer `snellius_vllm` before falling back to local or hosted models. The repo does not submit Snellius jobs automatically; the generated script is dry-run-safe and contains no credentials.

## Review A Paper

```bash
python -m hackathon_agents.cli review-paper path/to/paper.txt \
  --domain chem_bio \
  --focus-question "Are controls and replicates described?"
```

Supported inputs are `.txt`, `.md`, `.pdf`, and `.docx`. PDF extraction uses `pypdf`; DOCX extraction uses `python-docx`. The output is a structured JSON review with metadata, detected sections, claim-like statements, strengths, limitations, reproducibility checklist items, focus-question evidence, and a deterministic recommendation.

## Mechanism Discovery Workflow

The `Mechanism Discovery Agent Workbench` extends the generic scaffold with a closed-loop workflow for inferring plausible reaction mechanisms from kinetic experiment data:

```text
literature prior -> mechanism hypothesis generation -> mechanistic class proposal
-> kinetic experiment design -> robot experiment submission -> data ingestion
-> kinetic model fitting -> RL / active learning update -> DFT request if needed
-> critic / uncertainty check -> next experiment recommendation -> report
```

The workflow is bounded by an explicit `--rounds` value. It never runs an infinite autonomous loop, and all external systems are mockable by default.

Run the mock loop:

```bash
python -m hackathon_agents.cli mechanism-loop \
  --objective "Infer mechanism for photochemical reaction A + B -> P" \
  --rounds 3 \
  --mode mock
```

Run one analysis pass on existing kinetic data:

```bash
python -m hackathon_agents.cli mechanism-once \
  --data path/to/kinetics.csv \
  --objective "Infer mechanism"
```

Outputs are written to `runs/mechanism_<timestamp>/` or `runs/mechanism_once_<timestamp>/`:

- `state.json`
- `hypotheses.json`
- `experiments.json`
- `datasets/*.json` and `datasets/*.csv`
- `dft_jobs/*.json`
- `report.json`
- `report.docx`
- `trace.log`

Mock mode uses `MockRobotClient`, `MockHPCClient`, and local mock literature text. The robot mock generates synthetic time-resolved concentration data from a hidden toy mechanism, fits each hypothesis with SciPy `least_squares`, ranks hypotheses, recommends the next experiment, and writes JSON/DOCX reports.

Dry-run mode avoids real robot and cluster submissions. It still uses mock kinetic data, but the HPC backend writes SLURM submission scripts under the run directory instead of calling `sbatch`.

Real robot mode is opt-in only. Use `--mode real --allow-real-robot --robot-base-url ...` after implementing project-specific HTTP semantics in `src/hackathon_agents/tools/robot_client.py`. Without the explicit flag, `HTTPRobotClient` refuses to submit.

Real HPC submission is also opt-in. `SlurmHPCClient` writes scripts by default. Passing `--allow-hpc-submit` allows the client to call the configured submit command, but the repo does not hardcode cluster partitions, accounts, credentials, or ORCA paths.

To add a new mechanism class:

1. Add the class to `src/hackathon_agents/mechanism/mechanism_classes.py`.
2. Add hypothesis details in `src/hackathon_agents/mechanism/hypothesis.py`.
3. Add or map a kinetic model in `src/hackathon_agents/mechanism/kinetic_fitting.py`.
4. Add a focused test using synthetic data.

To add a new kinetic model, keep the graph contract unchanged and extend `fit_hypothesis_to_dataset()` or route a mechanism class to a new deterministic fitting function. Prefer identifiable models with fewer parameters before adding JAX, PyTorch, or richer ODE solvers.

To connect a real robot, subclass or complete `HTTPRobotClient` with the scheduler payload, authentication, status polling, and result-fetching semantics for your platform. It must return either a `KineticDataset` or a CSV/JSON path parseable by `kinetics_io`.

To connect SLURM/HPC, configure `SlurmHPCClient` with a project submission directory and command, then customize script generation in `src/hackathon_agents/tools/hpc_client.py`. Keep result parsing separate from submission so dry runs remain useful.

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
