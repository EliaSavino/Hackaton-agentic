# Implementation Roadmap

This roadmap turns the repo critique into focused implementation steps. The goal
is to make the workbench less like a linear demo scaffold and more like a
traceable scientific agent system that can ingest small datasets, plan typed
work, execute tools, validate outputs, and write useful artifacts.

## 1. Typed Planner Task Graph

### Why

The current discovery graph is mostly linear: planner, chemist, tools, critic,
writer, with a bounded loop. That is easy to test, but it makes the planner's
intent hard to inspect and makes targeted retries difficult. A typed task graph
lets the planner describe what should happen before it happens.

### Implementation Steps

1. Add task graph schema types for planned tasks and dependencies.
2. Extend the planner to emit a default task graph in state metadata.
3. Keep the existing LangGraph topology intact, but let downstream nodes record
   which planned task they satisfy.
4. Add tests that verify a request produces ingest, hypothesis, tool, critic,
   and reporting tasks.

## 2. Tool Registry For Planner And Critic

Status: implemented for the discovery planner and critic. The registry now
captures enabled state, run-mode gating, categories, inputs, outputs, failure
modes, mock behavior, side effects, execution risk, and safe config fields. The
planner and critic both receive the registry in model-backed payloads, and runs
store a registry snapshot plus summary in metadata.

### Why

Tools already exist, but the planner does not have a compact machine-readable
view of tool affordances. It should know which tools are enabled, what they do,
whether they are mock-safe, and what artifacts they can produce.

### Implementation Steps

1. Add a small registry builder that summarizes configured tools.
2. Include provider, enabled status, execution mode, inputs, outputs, and common
   failure modes where known.
3. Attach the registry snapshot to run metadata.
4. Let planner prompts and critic prompts include the registry in future model
   backed modes.

## 3. Provenance And Artifact Index

Status: implemented for discovery, mechanism, and system benchmark runs. The
artifact index now records schema version, generation time, deduplicated
artifacts, missing artifacts, file sizes, SHA-256 hashes, workflow provenance,
tool/model call summaries, planner task summaries, and workflow-specific counts.

### Why

Scientific outputs need traceability. Each report, CSV, plot, state file, model
call, and tool result should be discoverable from a single index.

### Implementation Steps

1. Add a run artifact index writer.
2. Record artifacts with path, kind, producer, description, and optional
   provenance metadata.
3. Call the index writer from graph/reporting nodes after files are written.
4. Include model calls and tool result counts in the run index.
5. Add tests that verify a run writes `artifact_index.json`.

## 4. Realistic System Benchmarks

Status: implemented as `benchmark-system`. The suite now runs named benchmark
cases for kinetic CSV to mechanism report, SMILES to descriptor table, paper
snippet to structured review, and numeric statistics/regression. Each case
records criteria, duration, metrics, warnings, errors, and artifacts, and the
artifact index records case-level provenance.

### Why

Model benchmarks alone do not test the system. The repo needs small end-to-end
benchmarks that exercise parsing, tools, reasoning, reporting, and validation.

### Implementation Steps

1. Add a system benchmark module with small deterministic tasks:
   - kinetic CSV to mechanism report,
   - SMILES list to descriptor table,
   - text paper snippet to structured review.
2. Write benchmark results as JSON under `runs/`.
3. Expose a CLI command such as `benchmark-system`.
4. Add smoke tests for the benchmark command.

## 5. Output Validators

Status: implemented for model JSON, model benchmark scoring, and generated
LaTeX reports. JSON output is normalized through one shared validator that can
strip markdown fences and recover embedded JSON objects. Model benchmarks record
whether JSON had to be repaired. The LaTeX writer validates generated reports
before writing artifacts and returns validation errors/warnings in the tool
result.

### Why

Some model outputs are structurally close but not directly usable, such as JSON
inside markdown fences or LaTeX with markdown wrappers. Validators should detect
and repair simple formatting problems before downstream code rejects them.

### Implementation Steps

1. Add helpers to strip markdown fences from JSON and LaTeX-like outputs.
2. Use the JSON helper in model benchmark compliance scoring.
3. Add a LaTeX validator that checks for basic section/table syntax and illegal
   markdown fences.
4. Add focused tests for fence stripping and validation.

## 6. Remote And HPC Execution Polish

### Why

The repo can generate Snellius scripts, but users need an obvious path for both
batch workflows and remote model-serving workflows.

### Implementation Steps

1. Add a dedicated HPC run guide.
2. Document two modes:
   - run repo workflows as Slurm jobs,
   - serve a model on HPC and tunnel it to local `prompt-terminal`.
3. Add an example generic Slurm script for `mechanism-once`.
4. Link the guide from the main docs index.

## Work Order

1. Implement output validators first because they improve benchmarks with small
   risk.
2. Add artifact indexing and provenance because it strengthens every workflow.
3. Add the tool registry and attach it to planner metadata.
4. Add the system benchmark command.
5. Add HPC documentation.
6. Expand the typed planner task graph once the lower-level metadata is in
   place.
