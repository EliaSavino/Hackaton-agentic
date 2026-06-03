# Quickstart

## Install

Use Conda if you want RDKit and scientific dependencies with the least friction:

```bash
conda env create -f environment.yml
conda activate hackathon-agents
cp .env.example .env
```

Use `uv` if you prefer Python package tooling:

```bash
uv sync
cp .env.example .env
```

## Configure Environment

Edit `.env`:

```bash
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
LITELLM_MODEL_DEFAULT=local_small
HACKATHON_RUN_MODE=cheap
OLLAMA_BIG_HOST=localhost
OLLAMA_SMALL_HOST=localhost
```

Hosted keys are optional if you are running `offline` mode with Ollama. The app should remain functional without internet access as long as local Ollama models are available.

## Run The Discovery Demo

```bash
PYTHONPATH=src python -m hackathon_agents.cli demo \
  "Find promising substrate candidates for reaction X" \
  --run-mode cheap \
  --max-iterations 3 \
  --min-valid-candidates 10 \
  --score-threshold 0.75
```

Outputs are written to `runs/<timestamp>/`.

Expected artifacts:

- `state.json`: full structured run state.
- `report.docx`: scientific report, if `python-docx` is installed.
- `descriptors.csv`: descriptor table, if RDKit is installed.
- `qed_plot.png`: simple plot, if plotting succeeds.
- ORCA input files when ORCA wrapper is enabled.

## Review A Paper

```bash
PYTHONPATH=src python -m hackathon_agents.cli review-paper path/to/paper.txt \
  --domain chem_bio \
  --focus-question "Are controls and replicates described?"
```

Supported inputs:

- `.txt`
- `.md`
- `.pdf`, with `pypdf`
- `.docx`, with `python-docx`

The output is a JSON review artifact with claims, evidence snippets, reproducibility checks, limitations, strengths, and a deterministic recommendation.

## Check Models

```bash
PYTHONPATH=src python -m hackathon_agents.cli check-models
```

This checks hosted key presence and pings configured Ollama servers.

## Benchmark Models

```bash
PYTHONPATH=src python -m hackathon_agents.cli benchmark-models
```

Benchmark results are saved to `runs/model_benchmark_<date>.json`.

## Run Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

Some tests are skipped when optional local dependencies such as RDKit or `python-docx` are not installed.
