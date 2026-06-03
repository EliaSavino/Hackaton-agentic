# Agents

Agents are thin state transformers. They should not be autonomous scripts.

## Existing Agents

- `planner`: creates a deterministic plan.
- `chemist`: seeds and refines candidate molecules.
- `critic`: ranks candidates and decides whether another pass is needed.
- `writer`: delegates report generation.
- `dft`: placeholder for computational chemistry orchestration.
- `coder`: placeholder for small code-generation tasks.
- `paper_reviewer`: configured prompt for paper review workflows.

## Add A New Agent

1. Add config in `configs/agents.yaml`.
2. Add a module in `src/hackathon_agents/agents/`.
3. Add or update state fields if needed.
4. Wire the node into `src/hackathon_agents/graph.py` if it belongs in the main graph.
5. Add a smoke test.

Example config:

```yaml
biologist:
  requires: [reasoning, biology]
  preferred_model: local_large
  fallback: [frontier_reasoning]
  temperature: 0.1
  max_tokens: 1200
  system_prompt: |
    You are a biological plausibility reviewer.
    Check assay relevance, biological controls, and overclaiming.
```

Example module:

```python
from hackathon_agents.state import DiscoveryStatePayload


def run(state: DiscoveryStatePayload) -> DiscoveryStatePayload:
    state.append_message("biologist: reviewed biological plausibility")
    return state
```

## System Prompts

System prompts belong in `configs/agents.yaml`.

Keep prompts:

- role-specific
- output-format specific
- explicit about uncertainty
- explicit about evidence requirements
- explicit about what not to invent

Avoid prompts that:

- ask for unbounded autonomy
- grant shell access
- bypass deterministic tools
- mix multiple unrelated roles

## Context Sharing

Share structured state, not raw transcripts.

Good context:

- original request
- plan
- candidate records
- summarized tool results
- critic decisions
- errors
- artifact paths

Avoid sharing:

- large raw logs
- full paper text when a section summary is enough
- model scratch text
- full DFT output in state
- irrelevant prior-agent chat history

## Reusing Agents

Reuse an agent when the role is the same but state has changed.

Example:

```text
chemist pass 1: broad candidate generation
chemist pass 2: generate alternatives from critic notes
chemist pass 3: fill missing property space
```

Create a new agent when the role changes.

Examples:

- `chemist` for molecular ideation.
- `biologist` for assay plausibility.
- `critic` for final scientific checks.
- `writer` for report assembly.

## Model Output Validation

When an agent calls a model, validate the output with Pydantic before mutating state.

Bad:

```python
state.metadata["model_json"] = json.loads(result.content)
```

Better:

```python
parsed = MySchema.model_validate_json(result.content)
state.metadata["validated_output"] = parsed.model_dump(mode="json")
```
