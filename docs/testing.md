# Testing

The test suite uses `unittest` to keep the scaffold simple.

Run:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

## Current Tests

- `test_config.py`: config loading and offline model routing.
- `test_critic_loop.py`: bounded critic loop decisions.
- `test_doc_writer.py`: DOCX report generation when `python-docx` is installed.
- `test_graph_smoke.py`: graph smoke path without DFT.
- `test_paper_review.py`: deterministic paper-review behavior.
- `test_tools_rdkit.py`: RDKit tools when RDKit is installed.

## Optional Dependency Skips

Some tests skip when optional packages are missing:

- RDKit tests skip if `rdkit` is unavailable.
- DOCX tests skip if `python-docx` is unavailable.

This is intentional. The scaffold should remain testable even when a laptop does not have every scientific package installed.

## What To Test For New Tools

For each new tool, test:

- normal success path
- invalid input path
- missing optional dependency if relevant
- structured `ToolResult` shape
- artifact creation if relevant
- timeout or unavailable executable behavior for external commands

## What To Test For New Agents

For each new agent, test:

- state fields are updated as expected
- errors are accumulated, not thrown
- model output is validated before use
- fallback behavior when model calls fail

## What To Test For Graph Changes

For graph topology changes, test:

- expected route is taken
- stop route works
- loop route works
- `max_iterations` is enforced
- `state.json` remains serializable

## Quick Verification Checklist

```bash
PYTHONPATH=src python -m unittest discover -s tests
python -m compileall src tests
python -c "import yaml; yaml.safe_load(open('configs/models.yaml')); yaml.safe_load(open('configs/agents.yaml')); yaml.safe_load(open('configs/tools.yaml'))"
```

Use a CLI smoke test after changing commands:

```bash
PYTHONPATH=src python -m hackathon_agents.cli --help
```
