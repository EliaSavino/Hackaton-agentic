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
SATURN_ENABLED=false
SATURN_REPO=
SATURN_PYTHON=python
SATURN_PRIOR=
BOLTZ_ENABLED=false
BOLTZ_EXECUTABLE=boltz
BOLTZ_RUN_MODE=local
BOLTZ_DEVICE=cpu
```

Do not put API keys in YAML or source code.

## Saturn Tool Config

`configs/tools.yaml` includes a `saturn` block for generative molecular design
(`schwallergroup/saturn`). It is disabled by default and reads its paths from the
environment so no install paths are hardcoded:

```yaml
saturn:
  enabled: ${SATURN_ENABLED:-false}
  saturn_repo: ${SATURN_REPO:-}
  saturn_python: ${SATURN_PYTHON:-python}
  prior_checkpoint: ${SATURN_PRIOR:-}
  timeout_seconds: 1800
  allow_run: false
  enabled_modes: [full, cheap]
```

Behavior:

- The `planner` proposes a default oracle (`qed` + `sa`) with no human input.
- The discovery graph gates Saturn with `config.tool_enabled("saturn")`, exactly
  like xTB/ORCA. When disabled, the chemist falls back to deterministic seeds.
- When Saturn is not installed (or the request uses `run=False`), the tool
  returns a deterministic mock candidate set so the pipeline stays offline-safe.
- Running the real Saturn model is opt-in: set `SATURN_ENABLED=true`, point
  `SATURN_REPO`/`SATURN_PYTHON`/`SATURN_PRIOR` at a cloned Saturn checkout and its
  conda environment, and set the Saturn input `run` flag to `true`.

## Boltz-2 Tool Config

`configs/tools.yaml` includes a `boltz_2` block for predicted protein-ligand structural co-folding and binding affinity:

```yaml
boltz_2:
  enabled: ${BOLTZ_ENABLED:-false}
  boltz_executable: ${BOLTZ_EXECUTABLE:-boltz}
  run_mode: ${BOLTZ_RUN_MODE:-local}
  device: ${BOLTZ_DEVICE:-cpu}
  single_sequence: true
  partition: gpu_a100
  allow_submit: false
  timeout_seconds: 1800
  enabled_modes: [full, cheap]
```

Behavior:

- Evaluates how generated ligands bind and co-fold with target proteins.
- Yieldspredicted 3D complex structures (PDB), confidence values (pLDDT, ipTM), and quantitative binding affinity ($\Delta G$ and $K_d$).
- Support zero-install mock fallback mode (used when `run=false` or local/HPC executable is absent).
- Real-model execution (local or submitted to HPC via sbatch) can be enabled with `BOLTZ_ENABLED=true`, `BOLTZ_RUN_MODE=slurm`, and `allow_submit=true`.
