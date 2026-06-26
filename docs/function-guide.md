# Function Guide

This guide covers the public functions, public classes, and CLI commands in
`src/hackathon_agents`. Names that start with `_` are private helpers and are
not intended to be called directly.

Most tool functions accept either a Pydantic input model or a plain `dict`.
Most tool functions return `ToolResult`:

```python
from hackathon_agents.tools.calculation_tools import convert_units

result = convert_units({"value": 5, "from_unit": "mg", "to_unit": "g"})
if result.ok:
    print(result.data)
else:
    print(result.error)
```

`ToolResult` fields:

- `ok`: `True` on success, `False` on recoverable failure.
- `data`: structured payload for the caller.
- `error`: error text when `ok` is false.
- `artifacts`: file paths created by the tool.
- `metadata`: optional extra audit details.

## Configuration

Import from `hackathon_agents.config`.

`load_config(config_dir="configs", env_file=".env", run_mode=None) -> AppConfig`
loads `.env`, YAML configs, expands environment references like `${VAR:-default}`,
and returns an `AppConfig`. Pass `run_mode` to override the configured mode.

`RunMode` is the execution mode enum: `full`, `no_dft`, `cheap`, and `offline`.
Use it to gate tools and model routing.

`ModelConfig` describes a model alias. Use:

- `model.litellm_model` for the LiteLLM model string.
- `model.api_base` for the resolved API base URL.
- `model.api_key` for the resolved API key from `api_key_env`.

`AgentConfig` stores one agent's preferred model, fallbacks, temperature,
token limit, requirements, and optional system prompt.

`ToolConfig.enabled_for_mode(run_mode)` returns whether a tool is enabled in a
given `RunMode`.

`ModelRoutingConfig` stores the default model aliases used by the router.

`AppConfig.get_model(alias)`, `AppConfig.get_agent(name)`, and
`AppConfig.tool_enabled(name)` are convenience lookups used by agents and the
graph.

## State And Shared Schemas

Import generic state from `hackathon_agents.state`.

`DiscoveryStatePayload` is the main graph state. Create it with an
`original_user_request`, then pass it through agents or `DiscoveryGraph`.

`DiscoveryStatePayload.append_message(message)` records a status message.

`DiscoveryStatePayload.add_error(message)` records an error and also appends an
`error: ...` message.

`DiscoveryStatePayload.add_tool_result(tool_name, result)` appends a
`ToolExecutionRecord`. If `result.ok` is false, it records a state error.

`DiscoveryStatePayload.run_path` returns `Path(run_dir)` when `run_dir` is set,
otherwise `None`.

Import common schemas from `hackathon_agents.schemas`.

`MoleculeRecord` represents a candidate molecule with `smiles`, optional
`name`, `source`, descriptors, score, notes, and metadata.

`MoleculeFilterConstraints` stores descriptor limits for molecule filtering.

`DiscoveryPlanStep` and `DiscoveryPlan` represent planner output.

`CriticDecision` represents whether the graph should loop again, why, requested
next actions, optional stop reason, valid candidate count, and best score.

`ToolResult` and `ToolExecutionRecord` are the standard tool result and audit
record models.

Paper review schemas in `hackathon_agents.schemas.papers` are:
`EvidenceSpan`, `PaperMetadata`, `PaperSection`, `PaperClaim`, `ReviewFinding`,
`ReproducibilityChecklistItem`, and `PaperReview`. They are Pydantic models used
by `review_paper`.

## Logging

Import from `hackathon_agents.logging_config`.

`configure_logging(level="INFO")` configures readable logging. It uses Rich
when installed and falls back to standard logging otherwise.

`get_logger(name, level=None)` returns a logger. The optional level can be
`"debug"`, `"info"`, or `"warning"`.

## Discovery Graph And Demo

Import from `hackathon_agents.graph` and `hackathon_agents.demos.discovery_demo`.

`build_graph(config) -> DiscoveryGraph` constructs the workflow wrapper.

`DiscoveryGraph.invoke(state) -> DiscoveryStatePayload` runs the planner,
chemist, tool execution, critic, and writer loop. `state` can be a
`DiscoveryStatePayload` or a dict compatible with that model.

`run_demo(request, run_mode=None, config_dir="configs", run_root="runs",
max_iterations=3, min_valid_candidates=10, score_threshold=0.75)` loads config,
builds the graph, runs it, and returns final state. It writes run artifacts
under `run_root`.

Example:

```python
from hackathon_agents.config import load_config
from hackathon_agents.graph import build_graph
from hackathon_agents.state import DiscoveryStatePayload

config = load_config(run_mode="cheap")
state = DiscoveryStatePayload(original_user_request="Find photoredox substrates")
result = build_graph(config).invoke(state)
print(result.final_report_path)
```

## Agents

Agent modules expose `run(...)` functions that accept and return
`DiscoveryStatePayload`. The graph calls them, but you can call them directly in
tests or notebooks.

`hackathon_agents.agents.planner.run(state, config=None)` creates a
`DiscoveryPlan` from the user request, optionally using a model-backed response
when configured.

`hackathon_agents.agents.chemist.run(state, config=None)` adds candidate
molecules. It can use model-backed JSON output or deterministic fallback
candidates.

`generate_parallel_hypotheses(request, count=50, workers=5,
model_alias="local_large")` returns deterministic `MoleculeRecord` suggestions
for cheap fanout.

`hackathon_agents.agents.coder.run(state)` records code-oriented next steps in
the state.

`hackathon_agents.agents.dft.run(state)` records DFT-oriented next steps in the
state.

`hackathon_agents.agents.critic.run(state, config=None)` evaluates candidates,
updates critic notes, and sets loop-control decisions.

`hackathon_agents.agents.writer.run(state)` writes final report artifacts.

`CandidateGenerationResponse`, `CriticReviewResponse`, and `AgentModelCall` are
Pydantic models used for model-backed agent outputs and audit metadata.

`call_agent_model(state=..., config=..., agent_name=..., task_type=...,
response_model=..., user_payload=..., expected_difficulty="medium",
system_prompt=None, max_tokens=None, temperature=None)` selects an agent model,
calls it through `LLMClient`, extracts JSON, validates it into `response_model`,
records audit metadata on state, and returns the parsed model or `None`.

## LLM Client, Routing, And Prompt Terminal

Import from `hackathon_agents.llm.client`, `hackathon_agents.llm.router`, and
`hackathon_agents.llm.prompt_terminal`.

`CompletionRequest` contains `model_alias`, chat `messages`, temperature,
`max_tokens`, retry count, fallback aliases, and metadata.

`CompletionResult` contains `ok`, content, resolved model alias, provider,
error, usage, cost, latency, and raw provider payload.

`LLMClient(config).complete(request)` resolves aliases from `AppConfig`, tries
fallback aliases, calls LiteLLM when available, and falls back to direct Ollama,
vLLM, or OpenRouter HTTP paths for supported providers.

`ModelSelectionRequest` describes a routing request: task type, difficulty,
context size, privacy requirement, budget mode, capabilities, and agent name.

`ModelSelection` is the chosen alias/provider/model plus the selection reason.

`ModelAvailability` records whether a configured model is reachable.

`ModelRouter(config).check_model_availability(timeout_seconds=2.0)` pings
configured model backends and stores availability by alias.

`ModelRouter(config).select(request)` picks a model from a
`ModelSelectionRequest` or dict.

`ModelRouter(config).select_for_agent(agent_name, task_type=None,
expected_difficulty="medium", context_size=0, privacy_required=False,
budget_mode=None)` builds a selection request from agent config and returns a
`ModelSelection`.

Prompt helper functions:

- `build_user_prompt(prompt, rag_context=None)` returns the prompt as-is, or
  wraps retrieved RAG context in a guarded prompt.
- `build_prompt_messages(prompt, system_prompt=None, history=None,
  rag_context=None)` returns OpenAI-style chat messages.
- `trim_history(history, max_messages=12)` keeps the latest messages.
- `terminal_metadata(model_alias, rag_enabled, rag_result_count=0)` returns
  metadata for prompt-terminal calls.

`benchmark_models(config, run_root="runs")` runs configured model checks and
writes a JSON benchmark artifact.

## RAG

Import the store from `hackathon_agents.rag` or `hackathon_agents.rag.store`.
Import tool wrappers from `hackathon_agents.tools.rag_tools`.

`RAGStore(db_path)` is a small SQLite lexical retrieval store.

`RAGStore.initialize()` creates tables if needed.

`RAGStore.ingest_path(path, extensions=None, chunk_size=700,
chunk_overlap=100, max_chars=2000000, replace=True, metadata=None)` indexes a
file or directory and returns counts plus skipped files.

`RAGStore.ingest_text(text, title, source_path=None, source_type="text",
metadata=None, chunk_size=700, chunk_overlap=100, replace=True)` indexes raw
text directly.

`RAGStore.search(query, limit=5, min_score=0.0)` returns a list of
`RAGSearchResult`.

`RAGStore.build_context(query, limit=5, max_chars=4000)` returns a bounded text
context plus result metadata.

`RAGStore.stats()` returns database counts.

Tool wrappers:

- `ingest_rag_documents(input_data)` indexes documents and returns `ToolResult`.
- `search_rag(input_data)` searches and returns records in `ToolResult.data`.
- `build_rag_context(input_data)` returns bounded context in `ToolResult.data`.

The RAG tool input models are `RAGIngestInput`, `RAGSearchInput`, and
`RAGContextInput`.

Example:

```python
from hackathon_agents.rag import RAGStore

store = RAGStore("data/rag.sqlite")
store.ingest_text("Photoredox rates depend on light intensity.", title="note")
print(store.search("light intensity", limit=1)[0].snippet)
```

## Mechanism Discovery

Import mechanism schemas from `hackathon_agents.mechanism.schemas`.

`LiteraturePrior` stores prior text, key findings, citations, limitations, and
source.

`MechanismHypothesis` stores a schema-valid mechanism hypothesis with species,
steps, rate law, assumptions, predicted signatures, confidence, uncertainty,
DFT requirements, and falsifying experiments.

`KineticExperimentVariables` stores controllable experiment variables.

`KineticExperiment` stores one proposed experiment and robot protocol metadata.

`KineticDataset` stores time points and concentration profiles. Its
`validate_profile_lengths()` model validator requires non-empty, sorted time
points and profile lengths aligned to the time grid.

`FitResult`, `MechanismRanking`, and `CriticAssessment` store fit output,
ranked hypotheses, and critic notes.

`MechanismClass` is the enum of supported mechanism classes.

`all_mechanism_classes()` returns the mechanism labels in enum order.

Hypothesis functions:

- `generate_initial_hypotheses(objective, prior=None)` returns five
  deterministic `MechanismHypothesis` objects.
- `generate_hypothesis_json(objective, prior=None)` returns those hypotheses as
  JSON.
- `validate_hypothesis_json(raw_json, retry_json=None)` validates JSON into a
  list of hypotheses and can retry once with a second payload.

Experiment design:

- `RLExperimentDesigner().propose_next_experiment(objective=..., hypotheses=...,
  rankings=..., round_index=...)` returns a bounded `KineticExperiment`.
- `ActiveLearningPolicy` is the protocol a learned policy should implement.
- `PlaceholderRLPolicy(policy_uri).propose_next_experiment(...)` raises until a
  real backend is connected.

Kinetic fitting:

- `fit_hypothesis_to_dataset(hypothesis, dataset)` fits one toy model and
  returns `FitResult`.
- `fit_all_hypotheses(hypotheses, dataset)` fits all hypotheses.
- `simulate_kinetic_dataset(experiment, mechanism_class=..., noise_level=0.005,
  seed=7)` creates deterministic mock kinetic traces.

Uncertainty and critic:

- `rank_hypotheses(hypotheses, fit_results)` combines prior confidence and fit
  quality into sorted `MechanismRanking` objects.
- `build_critic_assessment(round_index=..., rankings=..., fit_results=...,
  experiment=..., dft_jobs=...)` returns deterministic plausibility,
  overfitting, identifiability, missing-control, DFT, and robot notes.

Mechanism state:

- `MechanismDiscoveryState.run_path` returns the run directory as a `Path`.
- `add_error(message)` records a recoverable error.
- `add_validation_error(message)` records validation failure and also records an
  error.
- `save_json(path=None)` writes the state JSON. Without `path`, `run_dir` must
  be set.

Mechanism graph:

- `MechanismDiscoveryGraph.from_mode(...)` creates a graph with mock, dry-run,
  or real backends.
- `MechanismDiscoveryGraph.run_loop(...)` runs a bounded closed loop.
- `MechanismDiscoveryGraph.run_once(...)` analyzes existing kinetic data once.
- `run_mechanism_loop(...)` is the CLI-friendly loop entrypoint.
- `run_mechanism_once(...)` is the CLI-friendly one-pass entrypoint.
- `write_mechanism_report(state)` writes JSON and DOCX report artifacts and
  returns their paths.

Example:

```python
from hackathon_agents.mechanism.hypothesis import generate_initial_hypotheses
from hackathon_agents.mechanism.kinetic_fitting import simulate_kinetic_dataset, fit_all_hypotheses
from hackathon_agents.mechanism.experiment_design import RLExperimentDesigner
from hackathon_agents.mechanism.uncertainty import rank_hypotheses

hypotheses = generate_initial_hypotheses("photoredox reaction A + B to P")
experiment = RLExperimentDesigner().propose_next_experiment(
    objective="photoredox reaction A + B to P",
    hypotheses=hypotheses,
    rankings=[],
    round_index=0,
)
dataset = simulate_kinetic_dataset(experiment)
rankings = rank_hypotheses(hypotheses, fit_all_hypotheses(hypotheses, dataset))
print(rankings[0].title)
```

## Tool Base

Import from `hackathon_agents.tools.base`.

`BaseTool` is the abstract class for class-based tools. Implement `run()`.

`ok_result(data=None, artifacts=None)` builds a successful `ToolResult`.

`error_result(error, data=None, artifacts=None)` builds a failed `ToolResult`.

## Calculation Tools

Import from `hackathon_agents.tools.calculation_tools`.

The input models are `ExpressionInput`, `UnitConversionInput`,
`ReactionYieldInput`, `ThermochemistryInput`, `DilutionInput`,
`BufferPHInput`, and `MassMolesInput`.

`calculate_expression(input_data)` evaluates a safe math expression with
variables. Supported names include common math functions and constants such as
`sin`, `cos`, `sqrt`, `log`, `pi`, and `e`.

`convert_units(input_data)` converts among amount (`mol`, `mmol`, `umol`),
mass (`g`, `mg`, `ug`), volume (`l`, `ml`, `ul`), time (`s`, `min`, `h`),
molar energy (`kJ/mol`, `kcal/mol`), and molecular energy (`eV`, `hartree`).
It rejects incompatible dimensions.

`calculate_reaction_yield(input_data)` determines limiting reactant,
theoretical product, optional actual product moles, and percent yield.

`thermochemistry(input_data)` supports `arrhenius_rate`, `eyring_rate`,
`delta_g_from_keq`, and `keq_from_delta_g`.

`calculate_dilution(input_data)` solves one missing value from
stock concentration, stock volume, final concentration, and final volume.

`calculate_buffer_ph(input_data)` applies Henderson-Hasselbalch.

`convert_mass_moles(input_data)` converts between mass and moles from molar
mass. Provide exactly one of `mass` or `moles`.

## Statistics Tools

Import from `hackathon_agents.tools.statistics_tools`.

The input models are `SeriesInput`, `LinearRegressionInput`,
`GroupComparisonInput`, `BootstrapCIInput`, `CorrelationInput`,
`OutlierDetectionInput`, `OneWayAnovaInput`, and
`ClassificationMetricsInput`.

`describe_series(input_data)` summarizes numeric values from `values` or from
`rows` plus `column`.

`linear_regression(input_data)` returns slope, intercept, fitted values,
residuals, RMSE, and R squared.

`compare_groups(input_data)` returns group means, difference, fold change,
Welch-style t statistic, and Cohen's d.

`bootstrap_confidence_interval(input_data)` returns a deterministic bootstrap
interval for a named statistic. It accepts iterations, confidence level, and
seed.

`correlation(input_data)` returns Pearson or Spearman correlation.

`detect_outliers(input_data)` detects outliers by IQR or z score.

`one_way_anova(input_data)` returns ANOVA sums of squares, degrees of freedom,
F statistic, eta squared, and group means.

`classification_metrics(input_data)` returns binary classification metrics for
`y_true`, `y_pred`, and `positive_label`.

## DFT And Quantum Chemistry Tools

Import schemas from `hackathon_agents.tools.dft_job`.

`DFTCalculationType` enum values are `optimization`, `frequency`,
`single_point`, and `transition_state`.

`DFTJob` describes a DFT request.

`DFTResult` describes parsed or stubbed DFT output.

Import functions from `hackathon_agents.tools.dft_tools`.

The input models are `DFTPlanInput`, `DFTInputRenderInput`,
`DFTOutputParseInput`, `DFTEnergyComparisonInput`, and
`StationaryPointCheckInput`.

`plan_dft_jobs(input_data)` creates optimization and single-point jobs, with
optional frequency and transition-state jobs.

`render_dft_input(input_data)` renders an ORCA input string and optionally
writes it to `output_dir`.

`parse_dft_output(input_data)` parses energy, frequencies, diagnostics, and
summary from `output_text` or `output_path`.

`compare_dft_energies(input_data)` ranks energies, computes relative energies,
Boltzmann weights, and populations.

`check_stationary_point(input_data)` classifies frequencies as minimum,
transition-state candidate, or higher-order saddle.

ORCA wrapper functions in `hackathon_agents.tools.orca`:

- `OrcaInput` is the Pydantic input model.
- `check_orca_availability(executable="orca")` checks `PATH`.
- `generate_orca_input(input_data)` writes an ORCA `.inp` file.
- `run_orca(input_data)` writes input and optionally runs ORCA. Set `run=False`
  for dry-run input generation.

xTB wrapper functions in `hackathon_agents.tools.xtb`:

- `XtbInput` is the Pydantic input model.
- `check_xtb_availability(executable="xtb")` checks `PATH`.
- `run_xtb(input_data)` runs xTB with an XYZ path, work directory, arguments,
  and timeout.

HPC clients in `hackathon_agents.tools.hpc_client`:

- `HPCClient` is the abstract interface.
- `MockHPCClient.submit_job(job)`, `get_status(job_id)`, and
  `fetch_results(job_id)` provide deterministic offline DFT results.
- `SlurmHPCClient(submit_dir, allow_submit=False,
  submit_command="sbatch")` writes SLURM scripts. `submit_job(job)` only calls
  `sbatch` when `allow_submit=True`. `write_submission_script(job)` writes the
  script path.

## File, Plot, Report, And Memory Tools

Import from `hackathon_agents.tools.file_io`.

`read_json(path)` reads JSON into `ToolResult.data["content"]`.

`write_json(path, content)` writes pretty sorted JSON and returns the path as an
artifact.

`read_csv(path)` reads rows with `csv.DictReader`.

`write_csv(path, rows, fieldnames=None)` writes rows. If `fieldnames` is absent,
fields are inferred and sorted.

Import from `hackathon_agents.tools.plotting`.

`PlotInput` is the Pydantic input model.

`generate_plot(input_data)` creates a line, scatter, or bar plot from inline
`data` or `csv_path`, using `x_key`, `y_key`, and `output_path`.

Import from `hackathon_agents.tools.doc_writer`.

`ReportInput` is the Pydantic input model.

`write_scientific_report(input_data)` writes a DOCX report from a report title,
request, plan, candidates, tool results, critic notes, and output path.

Import from `hackathon_agents.tools.latex_writer`.

`LatexReportInput` is the Pydantic input model.

`write_latex_report(input_data)` writes a LaTeX report from similar structured
report data.

Import from `hackathon_agents.tools.memory_writer`.

`MemoryEntryInput` is the Pydantic input model.

`append_project_memory(input_data)` appends one event to a JSONL memory file and
optionally regenerates a Markdown summary.

## Literature And Paper Review Tools

Import from `hackathon_agents.tools.literature_search`.

`search_literature_prior(objective, mode="mock", local_text=None,
corpus_dir=None, limit=5)` returns a `LiteraturePrior`. With `corpus_dir`, it
uses local lexical search. Otherwise it returns mock or dry-run prior text.

Import from `hackathon_agents.tools.literature_stub`.

`search_literature_stub(query, limit=5)` returns deterministic stub literature
records.

Import from `hackathon_agents.tools.literature_tools`.

The input models are `LocalCorpusSearchInput`, `EvidenceTableInput`,
`CitationFormatInput`, `LiteratureRecordRankInput`, `LiteratureDedupInput`, and
`KeyTermExtractionInput`.

`search_local_corpus(input_data)` ranks local `.txt`, `.md`, and related text
documents by lexical match.

`build_evidence_table(input_data)` compares claims to snippets and labels
support strength.

`format_citations(input_data)` renders compact citations or BibTeX.

`rank_literature_records(input_data)` ranks record dictionaries by query match
and optional include/exclude screens.

`deduplicate_literature_records(input_data)` removes duplicate literature
records by DOI, title, and token overlap.

`extract_key_terms(input_data)` returns frequent terms and bigrams from text.

Import from `hackathon_agents.tools.paper_review`.

`PaperTextInput` and `PaperReviewInput` are the Pydantic input models.

`load_paper_text(input_data)` loads `.txt`, `.md`, `.pdf`, or `.docx`, or uses
inline text. `PaperTextInput.require_path_or_text()` enforces that one source
exists.

`split_paper_sections(input_data)` returns detected paper sections.

`review_paper(input_data)` returns a structured deterministic `PaperReview` and
can write JSON to `output_path`.

`batch_review_papers(paths, output_dir=None, domain="chem_bio")` reviews many
papers and writes output files.

## Kinetics, Robot, And Mechanism I/O Tools

Import from `hackathon_agents.tools.kinetics_io`.

`parse_kinetics_file(path, experiment_id=None)` reads `.csv` or `.json` kinetic
traces into a `KineticDataset`. CSV files need a time column named `time`,
`time_s`, `t`, or a first column that can serve as time.

`write_kinetic_dataset(dataset, output_dir)` writes JSON and CSV artifacts and
returns their paths.

Robot clients in `hackathon_agents.tools.robot_client`:

- `RobotClient` is the abstract interface.
- `MockRobotClient(hidden_mechanism=..., noise_level=0.005)` generates
  synthetic kinetic data. Use `submit_experiment`, `get_status`, and
  `fetch_results`.
- `HTTPRobotClient(base_url, api_key=None, allow_real_submissions=False)` is a
  placeholder for project-specific real robot semantics. It refuses submission
  unless explicitly enabled.

## RDKit, Python Execution, And External BO Tools

Import from `hackathon_agents.tools.rdkit_tools`.

`validate_smiles(smiles)` returns whether RDKit can parse the SMILES.

`compute_descriptors(smiles)` returns descriptors such as molecular weight,
LogP, TPSA, HBD/HBA, rotatable bonds, rings, formal charge, QED, and formula
when RDKit is installed.

`filter_molecules(smiles_list, constraints=None)` validates molecules, computes
descriptors, applies `MoleculeFilterConstraints`, and returns pass/fail rows.

Import from `hackathon_agents.tools.python_exec`.

`PythonExecInput` is the Pydantic input model.

`run_python(input_data)` executes a bounded Python snippet in a subprocess with
safe builtins, `math`, and `statistics`. It blocks imports, dunder attributes,
and dangerous builtins, and returns stdout plus public variables.

Import from `hackathon_agents.tools.robrains_bo`.

`check_robrains_availability(input_data=None)` checks the RoBrains repository
path, importability, backend availability, and capabilities availability.

`list_robrains_capabilities(input_data=None)` calls RoBrains
`LocalBackendAPI.get_capabilities()` when available.

`suggest_robrains_experiments(input_data)` builds parameters, objective signs,
observation data, runs RoBrains Bayesian optimization, and returns suggested
experiments. The default repository path is `/Users/es/GitHub/RoBrains` unless
overridden.

RoBrains input models:

- `RoBrainsAvailabilityInput(repo_path=None)`.
- `RoBrainsParameterSpec(name, kind="continuous", min_value=None,
  max_value=None, values=[], unit="-")`. Continuous parameters need min and max;
  categorical and discrete parameters need values.
- `RoBrainsObjectiveSpec(name, direction="maximize")`.
- `RoBrainsSuggestionInput(parameters, objectives, observations=[],
  output_dir="runs/robrains_bo", batch_size=1, initial_points=None,
  total_points=None, model="SingleTaskGP", acquisition_function="UCB",
  initialisation_method="LHS", force_categorical=False,
  explorative_factor=None)`.

## Snellius vLLM And Gateway Tools

Import from `hackathon_agents.tools.snellius_vllm`.

`generate_snellius_vllm_job(input_data)` writes a dry-run-safe SLURM script for
serving vLLM and returns paths plus connection metadata.

`render_snellius_vllm_job(input_data)` returns the same script text without
writing it.

`generate_snellius_gateway_job(input_data)` writes a vLLM plus LiteLLM gateway
SLURM script and companion LiteLLM config files.

`render_snellius_gateway_job(input_data)` returns the gateway script text
without writing it.

`render_snellius_litellm_config(input_data)` renders LiteLLM config text
without embedding provider secrets.

`render_snellius_client_env(input_data)` renders local SSH tunnel and Claude
Code environment commands.

The input models are `SnelliusVLLMJobInput`, `SnelliusLiteLLMConfigInput`,
`SnelliusGatewayJobInput`, and `SnelliusClientEnvInput`.

## CLI Commands

The installed script is `hackathon-agents`, equivalent to
`python -m hackathon_agents.cli`.

Commands:

- `demo REQUEST`: run the deterministic discovery demo.
- `benchmark-models`: benchmark configured models and write JSON output.
- `review-paper PATH`: review a `.txt`, `.md`, `.pdf`, or `.docx` paper.
- `rag-ingest PATH`: index documents into the SQLite RAG store.
- `rag-search QUERY`: search the RAG store. Add `--context` for prompt-ready
  context text.
- `prompt-terminal`: open an interactive chat terminal with optional RAG.
- `mechanism-loop --objective ...`: run the bounded mechanism discovery loop.
- `mechanism-once --data ... --objective ...`: analyze existing kinetic data.
- `check-models`: check configured model availability.
- `snellius-vllm-script`: generate a Snellius vLLM SLURM script.
- `snellius-gateway-script`: generate a Snellius vLLM plus LiteLLM gateway
  script.
- `snellius-client-env`: print local tunnel and client environment commands.

`main()` in `hackathon_agents.cli` invokes Typer when available and falls back
to an argparse implementation for core commands.
