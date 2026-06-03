# Graph And Iteration

The graph controls workflow. Agents update state. Tools do deterministic work.

## Current Topology

```text
planner
  -> chemist
  -> tool_execution
  -> critic
      -> chemist if needs_more_passes and iteration < max_iterations
      -> writer otherwise
```

LangGraph is used when installed. A deterministic fallback runner implements the same topology when LangGraph is unavailable.

## Loop State

Loop fields in `DiscoveryStatePayload`:

- `iteration`
- `max_iterations`
- `needs_more_passes`
- `requested_next_actions`
- `stop_reason`
- `critic_decisions`

The graph increments `iteration` at the start of each chemist pass.

## Critic Decision

The critic writes a typed `CriticDecision`:

```python
class CriticDecision(BaseModel):
    needs_more_passes: bool
    reason: str
    requested_next_actions: list[str]
    stop_reason: str | None
    valid_candidate_count: int
    best_score: float | None
```

The graph reads `needs_more_passes` and `iteration`.

## Stop Criteria

Current stop criteria:

- reached `max_iterations`
- RDKit descriptor tools unavailable
- too many accumulated tool errors
- candidate quality threshold met
- no material score improvement

Current continue criteria:

- valid candidate count below target
- best score below target and still worth improving

## CLI Loop Controls

```bash
PYTHONPATH=src python -m hackathon_agents.cli demo \
  "Find promising substrate candidates for reaction X" \
  --max-iterations 3 \
  --min-valid-candidates 10 \
  --score-threshold 0.75
```

These become state fields or metadata:

- `max_iterations`
- `metadata["min_valid_candidates"]`
- `metadata["score_threshold"]`

## Add A New Branch

Example: route to a `biologist` before writer.

1. Create `agents/biologist.py`.
2. Add state fields for biological findings.
3. Add node to graph:

```python
workflow.add_node("biologist", self._dict_node(self._biologist_node))
```

4. Route from critic:

```text
critic -> biologist -> writer
```

5. Add tests for both routes.

## Context Rules

The graph state is the shared context. Keep it structured and bounded.

Share:

- structured results
- concise notes
- artifact paths
- validated model outputs

Do not share:

- huge raw outputs
- every prior prompt and completion
- private scratch reasoning
- repeated duplicate tool outputs

## Debugging The Loop

Inspect:

```bash
runs/<timestamp>/state.json
```

Useful fields:

- `messages`
- `critic_decisions`
- `errors`
- `tool_results`
- `metadata.best_score`
- `metadata.valid_candidate_count`

If the loop stops too early, inspect `stop_reason`. If it loops too much, lower `max_iterations` or raise the quality thresholds.
