# Tools

Tools are deterministic units with typed inputs and structured outputs.

## ToolResult Contract

Every tool returns:

```python
ToolResult(
    ok=True,
    data={},
    error=None,
    artifacts=[],
    metadata={},
)
```

When a tool fails:

```python
ToolResult(
    ok=False,
    data={"path": "input.file"},
    error="Dependency is not installed.",
    artifacts=[],
)
```

## Current Tools

### RDKit

Module: `src/hackathon_agents/tools/rdkit_tools.py`

Functions:

- `validate_smiles(smiles)`
- `compute_descriptors(smiles)`
- `filter_molecules(smiles_list, constraints)`

Descriptors include molecular weight, LogP, HBD, HBA, TPSA, rotatable bonds, heavy atoms, ring count, and QED.

### Paper Review

Module: `src/hackathon_agents/tools/paper_review.py`

Functions:

- `load_paper_text(input)`
- `split_paper_sections(input)`
- `review_paper(input)`
- `batch_review_papers(paths, output_dir, domain)`

See [Paper Review](paper-review.md).

### Literature Tools

Module: `src/hackathon_agents/tools/literature_tools.py`

Functions:

- `search_local_corpus(input)`
- `build_evidence_table(input)`
- `format_citations(input)`
- `rank_literature_records(input)`
- `deduplicate_literature_records(input)`
- `extract_key_terms(input)`

These tools provide offline/local literature support: rank text or markdown documents by query relevance, screen structured literature records, map claims to snippets, deduplicate by DOI/title, extract key terms, and format compact or BibTeX-style citations. They do not make external API calls.

### RAG Tools

Module: `src/hackathon_agents/tools/rag_tools.py`

Functions:

- `ingest_rag_documents(input)`
- `search_rag(input)`
- `build_rag_context(input)`

These tools persist local `.txt`, `.md`, `.pdf`, and `.docx` content into a SQLite database, chunk documents, build a lexical index, and return bounded context blocks for prompt augmentation. The default database path is `data/rag.sqlite`.

CLI examples:

```bash
PYTHONPATH=src python -m hackathon_agents.cli rag-ingest docs --db-path data/rag.sqlite
PYTHONPATH=src python -m hackathon_agents.cli rag-search "photoredox light intensity" --context
PYTHONPATH=src python -m hackathon_agents.cli prompt-terminal --model-alias openrouter_general
```

### Python Execution

Module: `src/hackathon_agents/tools/python_exec.py`

Function:

- `run_python(input)`

This is safe-ish local Python execution for short snippets. It blocks imports, file IO, shell access, and common dangerous builtins by default. It enforces a timeout.

Do not use this as a security sandbox for untrusted users.

### File IO

Module: `src/hackathon_agents/tools/file_io.py`

Functions:

- `read_json(path)`
- `write_json(path, content)`
- `read_csv(path)`
- `write_csv(path, rows, fieldnames)`

### Plotting

Module: `src/hackathon_agents/tools/plotting.py`

Function:

- `generate_plot(input)`

Supports line, scatter, and bar plots from CSV-like records or a CSV path.

### DOCX Writer

Module: `src/hackathon_agents/tools/doc_writer.py`

Function:

- `write_scientific_report(input)`

Generates `.docx` directly through `python-docx`. It does not automate Microsoft Word.

### LaTeX Writer

Module: `src/hackathon_agents/tools/latex_writer.py`

Function:

- `write_latex_report(input)`

Generates an escaped `.tex` report from the same structured discovery state used by the DOCX writer. It does not require a TeX installation and does not compile PDFs.

### Memory Writer

Module: `src/hackathon_agents/tools/memory_writer.py`

Function:

- `append_project_memory(input)`

Appends compact workflow milestones to `data/memory/project_memory.jsonl` and regenerates a human-readable `data/memory/project_memory.md`. The graph uses it after major nodes so multiple users can inspect what has already been done without reading every run artifact.

### xTB

Module: `src/hackathon_agents/tools/xtb.py`

Functions:

- `check_xtb_availability(executable)`
- `run_xtb(input)`

If xTB is missing, the tool returns a structured unavailable result.

### ORCA

Module: `src/hackathon_agents/tools/orca.py`

Functions:

- `check_orca_availability(executable)`
- `generate_orca_input(input)`
- `run_orca(input)`

If ORCA is missing, the wrapper can still generate an input file and return a structured unavailable result.

### DFT Tools

Module: `src/hackathon_agents/tools/dft_tools.py`

Functions:

- `plan_dft_jobs(input)`
- `render_dft_input(input)`
- `parse_dft_output(input)`
- `compare_dft_energies(input)`
- `check_stationary_point(input)`

These helpers sit above the ORCA/xTB/HPC wrappers. They produce typed `DFTJob` plans, render ORCA input files without submitting anything, parse common energy/frequency lines from quantum chemistry output, rank relative energies with Boltzmann populations, and classify minima/transition-state candidates from frequencies.

### Calculation Tools

Module: `src/hackathon_agents/tools/calculation_tools.py`

Functions:

- `calculate_expression(input)`
- `convert_units(input)`
- `calculate_reaction_yield(input)`
- `thermochemistry(input)`
- `calculate_dilution(input)`
- `calculate_buffer_ph(input)`
- `convert_mass_moles(input)`

These are deterministic calculator utilities for short arithmetic, compatible unit conversions, limiting-reagent/yield calculations, basic Arrhenius/Eyring/equilibrium thermochemistry, C1V1 dilution math, Henderson-Hasselbalch buffer pH, and mass/moles conversions.

### Statistics Tools

Module: `src/hackathon_agents/tools/statistics_tools.py`

Functions:

- `describe_series(input)`
- `linear_regression(input)`
- `compare_groups(input)`
- `bootstrap_confidence_interval(input)`
- `correlation(input)`
- `detect_outliers(input)`
- `one_way_anova(input)`
- `classification_metrics(input)`

These cover common hackathon analysis needs: summary statistics, simple least-squares regression, Welch-style group comparison statistics, effect size, deterministic bootstrap intervals, Pearson/Spearman correlation, outlier detection, one-way ANOVA summaries, and binary classification metrics.

### RoBrains Bayesian Optimization

Module: `src/hackathon_agents/tools/robrains_bo.py`

Functions:

- `check_robrains_availability(input)`
- `list_robrains_capabilities(input)`
- `suggest_robrains_experiments(input)`

This tool wraps the local RoBrains checkout as a Bayesian optimization framework for the agent. By default it looks at `/Users/es/GitHub/RoBrains`; override with `ROBRAINS_REPO_PATH` or the per-call `repo_path` input.

`suggest_robrains_experiments` accepts parameter specs, objective specs, optional finished observations, and BO settings. With no observations it returns an initial design from RoBrains. With observations it uses RoBrains `SingleBayesianOptiBackend` to suggest the next experiment batch. RoBrains and its heavier BO dependencies are imported lazily, so normal agent startup still works when that environment is not installed.

### Snellius vLLM

Module: `src/hackathon_agents/tools/snellius_vllm.py`

Functions:

- `generate_snellius_vllm_job(input)`
- `render_snellius_vllm_job(input)`
- `generate_snellius_gateway_job(input)`
- `render_snellius_gateway_job(input)`
- `render_snellius_litellm_config(input)`
- `render_snellius_client_env(input)`

This writes a dry-run-safe SLURM script that starts `vllm serve` inside the Snellius Apptainer container. It does not submit to SLURM or assume credentials. After the job starts and the port is exposed or tunneled, set `SNELLIUS_VLLM_BASE_URL` so the `snellius_vllm` model alias can call the OpenAI-compatible `/v1/chat/completions` API.

For Claude Code, use `generate_snellius_gateway_job`. It writes a SLURM script plus LiteLLM configs for an Anthropic-compatible `/v1/messages` gateway. The full config exposes `claude-snellius-local` and `claude-snellius-hosted`; the local-only config is selected automatically if the server-side hosted key or outbound provider preflight is missing. Provider keys stay in the Snellius `.env`, and users connect through an SSH tunnel generated by `render_snellius_client_env`.

### Saturn (Generative Molecular Design)

Module: `src/hackathon_agents/tools/saturn_tools.py`

Functions:

- `check_saturn_availability(saturn_repo, saturn_python)`
- `build_saturn_config(input)`
- `generate_with_saturn(input)`
- `saturn_records(result_data)`

This wraps [`schwallergroup/saturn`](https://github.com/schwallergroup/saturn), a sample-efficient, language-model-based generative design framework. It lets an agent run goal-directed molecule generation against an **oracle (reward function) of its choice** and a chosen **agent/RL setting**, then recover the generated SMILES as typed `MoleculeRecord` objects.

Saturn is not a pip package: it is a separate cloned repository with its own conda environment (Python 3.10, GPU recommended) driven by a single JSON config (`python saturn.py config.json`). Because it cannot be imported in-process, this tool follows the xTB/ORCA/Snellius pattern:

1. Build a Saturn-compatible JSON config from a small typed schema (`SaturnGenerationInput`): the `oracle` list (each an `OracleComponent` with `name`, `weight`, `specific_parameters`), plus agent knobs like `aggregator`, `batch_size`, `n_steps`, `sigma`, `learning_rate`, `experience_replay_memory`, and `use_diversity_filter`.
2. Optionally run `saturn.py` as a subprocess in the Saturn repo using the Saturn interpreter (set `run=True`, `saturn_repo`, `saturn_python`, and a `prior_checkpoint`).
3. Parse SMILES + scores from Saturn's CSV logs into ranked `MoleculeRecord` objects.

When Saturn is unavailable or `run=False` (the default), the tool writes the config and returns a **deterministic mock** candidate set, so the workbench stays testable offline.

Configure it in `configs/tools.yaml` under `saturn` (disabled by default) or via env vars `SATURN_ENABLED`, `SATURN_REPO`, `SATURN_PYTHON`, `SATURN_PRIOR`.

The `chemist` agent can opt in by setting `state.metadata["saturn"]` to a dict of Saturn settings; otherwise it keeps its deterministic seed behavior. Example:

```python
state.metadata["saturn"] = {
    "oracle": [
        {"name": "qed", "weight": 1.0},
        {"name": "sa", "weight": 0.5},
    ],
    "aggregator": "product",
    "n_steps": 50,
    "batch_size": 64,
    "run": False,  # set True with saturn_repo/saturn_python to run the real model
}
```

### Boltz-2 (Molecular Co-Folding and Docking)

Module: `src/hackathon_agents/tools/boltz_tools.py`

Functions:

- `check_boltz_availability(executable)`
- `write_boltz_yaml_input(work_dir, job_id, sequence, smiles)`
- `render_boltz_slurm_script(parsed, yaml_path)`
- `run_boltz_2(input)`

This tool predicts how a generated small-molecule ligand co-folds and docks with a target protein, returning the predicted 3D structure (PDB), structural confidence (pLDDT, ipTM), and binding affinity ($\Delta G$ in kcal/mol and $K_d$ in nanomolar).

It supports three powerful execution settings:
1. **Local Mode**: Runs the local CLI `boltz predict ...` in a subprocess.
2. **SLURM HPC Mode**: Generates a production-grade batch submission script (`.slurm`) for clusters (like Snellius), and optionally submits it via `sbatch`.
3. **Mock Mode**: When `run=False` (default) or Boltz is not installed, it runs a high-fidelity deterministic simulation based on a hash of the sequence + ligand, returning custom binding affinities and mock 3D structures. This ensures the workflow is completely offline-safe and demo-ready.

Configure it in `configs/tools.yaml` under `boltz_2` or via environment variables: `BOLTZ_ENABLED`, `BOLTZ_EXECUTABLE`, `BOLTZ_RUN_MODE` (`local` or `slurm`), `BOLTZ_DEVICE`.

### BayBE (Bayesian Design of Experiments)

Module: `src/hackathon_agents/tools/baybe_tools.py`

Functions:

- `check_baybe_availability()`
- `recommend_experiments(input)`
- `build_search_space(parameters)`
- `build_objective(targets)`

This wraps [`emdgroup/baybe`](https://github.com/emdgroup/baybe), Merck KGaA's open-source Bayesian optimization / Design-of-Experiments toolbox. It answers the question: **"Given the knobs I can turn, the property I want to optimize, and the experiments I've already run, which experiments should I run next?"**

Where Saturn *invents* new molecules, BayBE *selects the most informative configurations* from a search space you define — reaction conditions, formulation ratios, process parameters, or which compound from a fixed library to test next. It is built for the low-/no-data regime, so it is useful from the very first experiment, and it pairs naturally with the expensive oracles in this workbench (xTB/ORCA energies, Boltz-2 affinities, RDKit descriptors): BayBE chooses *which* candidate to evaluate next to minimize oracle calls.

The tool is deliberately **stateless**: each call rebuilds the campaign from the `parameters`, `targets`, and the full `measurements` history passed in. The agent simply keeps appending measured rows and asking for the next batch — which fits the JSON-serializable state model used throughout the workbench.

Inputs (`BayBERecommendInput`) are written to be readable by chemists, not just agents:

- `parameters`: the experimental knobs. Each is one of:
  - `numerical_continuous` with `bounds: [low, high]` (e.g. temperature 25–80 °C),
  - `numerical_discrete` with `values: [...]` (e.g. pressures `[1, 5, 10]`),
  - `categorical` with `values: [...]` and optional `encoding` (`OHE`/`INT`),
  - `substance` with `data: {label: SMILES}` and `encoding` (`MORDRED`/`ECFP`/…) so BayBE reasons about chemical similarity.
- `targets`: one or more measured outcomes, each with `mode` (`MAX`, `MIN`, or `MATCH` + `match_value`) and a `weight`. Multiple targets automatically use a `DesirabilityObjective`; in that case each `MAX`/`MIN` target also needs `bounds: [low, high]` (its plausible value range) so it can be normalized onto a common scale before the targets are combined.
- `measurements`: experiments already run, each a single row mapping parameter **and** target names to values, e.g. `{"Temperature_C": 60, "Base": "KOtBu", "Yield": 78.5}`.
- `batch_size`: how many next experiments to recommend.

When BayBE is installed and the run is enabled, the tool builds a real `Campaign`, ingests the measurements, and calls BayBE's Bayesian (Gaussian-process / BoTorch) recommender. Otherwise — by default, or when BayBE is not installed — it returns a deterministic, space-filling **mock** recommendation set (skipping already-measured configurations), so the pipeline stays offline-safe and demo-ready.

Like xTB/ORCA/Saturn/Boltz, it is **disabled by default**. Configure it in `configs/tools.yaml` under `baybe` (`enabled`, `allow_run`, `enabled_modes`) or via the `BAYBE_ENABLED` env var. Install the optional dependency with `pip install 'baybe[chem,simulation]'` (or `pip install -e '.[baybe]'`).

An agent (or chemist) opts in by setting `state.metadata["baybe"]`; the graph then config-gates the call exactly like the other tools and supplies `work_dir` plus the `allow_run` flag. Example:

```python
state.metadata["baybe"] = {
    "parameters": [
        {"name": "Temperature_C", "type": "numerical_continuous", "bounds": [25, 80]},
        {"name": "Pressure_bar", "type": "numerical_discrete", "values": [1, 5, 10]},
        {"name": "Solvent", "type": "substance",
         "data": {"DMSO": "CS(=O)C", "Water": "O", "Methanol": "CO"},
         "encoding": "MORDRED"},
    ],
    "targets": [{"name": "Yield", "mode": "MAX"}],
    "measurements": [
        {"Temperature_C": 60, "Pressure_bar": 5, "Solvent": "DMSO", "Yield": 78.5},
    ],
    "batch_size": 3,
}
```

The recommended next experiments are written to `runs/<timestamp>/baybe/baybe_recommendations.csv` and stored in `state.metadata["baybe_recommendations"]`.

## Add A Tool

1. Define Pydantic input schema if the input is more than one or two primitives.
2. Implement a function in `src/hackathon_agents/tools/`.
3. Return `ToolResult` on every path.
4. Add config in `configs/tools.yaml`.
5. Add tests.

Example:

```python
from pydantic import BaseModel

from hackathon_agents.tools.base import error_result, ok_result


class MyToolInput(BaseModel):
    value: float


def run_my_tool(input_data: MyToolInput | dict):
    parsed = input_data if isinstance(input_data, MyToolInput) else MyToolInput.model_validate(input_data)
    try:
        return ok_result({"doubled": parsed.value * 2})
    except Exception as exc:
        return error_result(str(exc))
```

## Tool Design Rules

- No uncontrolled shell execution.
- Always set timeouts for external commands.
- Save large outputs to artifacts.
- Keep state small.
- Make missing dependencies a structured result.
- Prefer deterministic libraries over model-only parsing.
- Add tests for success and failure paths.
