# Architecture

The workbench is a typed, config-driven scaffold for scientific discovery agents.

## Main Components

```text
configs/*.yaml
  -> config loader
  -> model router
  -> graph
  -> agents
  -> tools
  -> typed state
  -> run artifacts
```

## Package Layout

```text
src/hackathon_agents/
  cli.py                 Command line entrypoints
  config.py              YAML and .env loading
  graph.py               LangGraph topology and fallback runner
  state.py               Shared Pydantic state
  logging_config.py      Rich logging fallback
  llm/
    client.py            LiteLLM wrapper
    router.py            Capability-based model routing
    benchmark.py         Model benchmark tasks
  agents/
    planner.py           Builds deterministic plan and default Saturn oracle
    chemist.py           Candidate molecule generation, refinements, Saturn hook
    critic.py            Scores candidates and controls loop decisions
    writer.py            Delegates report writing
    dft.py               DFT orchestration placeholder
    coder.py             Code-agent placeholder
  tools/
    rdkit_tools.py       SMILES validation and descriptors
    saturn_tools.py      Saturn generative molecular design wrapper
    paper_review.py      Structured deterministic paper review
    python_exec.py       Safe-ish Python snippets
    file_io.py           JSON/CSV IO
    plotting.py          Matplotlib plots
    doc_writer.py        DOCX report generation
    xtb.py               xTB availability and execution wrapper
    orca.py              ORCA input and execution wrapper
```

## Data Flow

The graph passes one `DiscoveryStatePayload` between nodes. Each node returns the updated state.

Current discovery graph:

```text
planner
  -> chemist
  -> tool_execution
  -> critic
      -> chemist if needs_more_passes and iteration < max_iterations
      -> writer otherwise
```

## State Contract

`DiscoveryStatePayload` lives in `src/hackathon_agents/state.py`.

Important fields:

- `original_user_request`: user task.
- `plan`: typed discovery plan.
- `candidate_molecules`: list of typed molecule records.
- `tool_results`: structured tool outputs.
- `errors`: accumulated failures and fallback notices.
- `critic_notes`: human-readable review notes.
- `critic_decisions`: typed loop decisions.
- `iteration`: current bounded pass count.
- `max_iterations`: hard loop cap.
- `needs_more_passes`: graph routing flag.
- `requested_next_actions`: what the next pass should do.
- `stop_reason`: final reason for stopping.
- `final_report_path`: report artifact path.
- `messages`: run log trail.
- `metadata`: small structured run settings and summaries.

## Tool Contract

Every tool should return:

```python
ToolResult(
    ok=True,
    data={},
    error=None,
    artifacts=[],
)
```

Rules:

- Never silently swallow errors.
- Do not crash the whole app when an optional executable or dependency is missing.
- Put file paths in `artifacts`.
- Put machine-readable outputs in `data`.
- Keep logs and raw blobs out of state when they are large. Save large outputs as artifacts and store summaries.

## Agent Contract

Agents should be thin:

- Read typed state.
- Read their config if needed.
- Optionally call `LLMClient`.
- Validate model output with Pydantic.
- Update state.
- Avoid direct file or shell work unless the operation belongs in a tool.

## Model Contract

Models are addressed by alias. Code should not hardcode provider-specific model names.

Use:

- `configs/models.yaml` for model backend definitions.
- `configs/agents.yaml` for agent preferences and prompts.
- `ModelRouter` for capability-based selection.
- `LLMClient` for LiteLLM calls and fallbacks.
