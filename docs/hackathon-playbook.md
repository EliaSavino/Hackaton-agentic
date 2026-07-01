# Hackathon Playbook

This repo is meant for uncertain scientific-discovery challenges. The safest strategy is to build many small deterministic capabilities and let agents orchestrate them.

## First Hour

1. Confirm dependencies.
2. Copy `.env.example` to `.env`.
3. Start local Ollama servers if available.
4. Run tests.
5. Run `check-models`.
6. Run `benchmark-models` if models are available.
7. Run one demo.

Commands:

```bash
conda env create -f environment.yml
conda activate hackathon-agents
cp .env.example .env
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m hackathon_agents.cli check-models
```

## When The Challenge Is About Molecules

Use or extend:

- RDKit validation
- descriptor calculation
- molecule filtering
- plotting
- DOCX and LaTeX report writers
- xTB and ORCA wrappers

Good next tools:

- reaction template matching
- similarity search
- scaffold clustering
- purchasability lookup stub
- ADMET heuristic filters
- docking wrapper with safe fallback

## When The Challenge Is About Papers

Use or extend:

- paper text loading
- section splitting
- claim extraction
- reproducibility checklist
- focus-question evidence
- structured paper-review JSON

Good next tools:

- local corpus search
- citation graph stub
- figure/table extraction stub
- paper comparison matrix
- evidence-to-claim mapper

## When The Challenge Is About Model Building

Add tools in phases:

1. Dataset validation.
2. Feature generation.
3. Train/test splitting.
4. Baseline model training.
5. Metrics and plots.
6. Report generation.

Recommended modules:

```text
src/hackathon_agents/tools/dataset_tools.py
src/hackathon_agents/tools/modeling.py
src/hackathon_agents/schemas/modeling.py
tests/test_modeling.py
```

Keep models simple at first:

- logistic regression
- random forest
- gradient boosting if available
- linear regression
- ridge/lasso

## When Internet Is Unavailable

Use:

- `offline` mode
- local Ollama aliases
- deterministic tools
- local files under `data/`
- literature stubs

Avoid:

- live web search dependencies
- external APIs
- assumptions about package downloads

## How To Decide What To Build Next

Prefer tools that:

- are deterministic
- can be tested with small fixtures
- produce structured output
- save artifacts
- do not require internet
- are useful across multiple challenge prompts

Avoid:

- large demos with fragile dependencies
- one-off prompt chains
- uncontrolled shell wrappers
- unbounded autonomous loops

## Demo Strategy

Use the graph to produce:

- a clear state trail
- candidate outputs
- deterministic tool evidence
- critic notes
- a report artifact

The judges should be able to inspect `runs/<timestamp>/state.json` and understand what happened.
