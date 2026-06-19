# Testing

The test suite uses `unittest` to keep the scaffold simple.

Run:

```bash
pytest -q
python -m compileall -q src tests
```

## Current Tests

- `test_config.py`: config loading and offline model routing.
- `test_cli_smoke.py`: source-tree CLI help and exposed integration flags.
- `test_critic_loop.py`: bounded critic loop decisions.
- `test_doc_writer.py`: DOCX report generation when `python-docx` is installed.
- `test_graph_smoke.py`: graph smoke path without DFT.
- `test_model_backed_agents.py`: mocked model-backed planner, chemist, and critic paths.
- `test_mechanism_graph_smoke.py`: closed-loop mechanism workflow artifacts.
- `test_mechanism_integrations.py`: local literature prior and configurable DFT structure hooks.
- `test_paper_review.py`: deterministic paper-review behavior.
- `test_rag_store.py`: local SQLite RAG indexing and search.
- `test_dft_tools.py`: DFT planning, rendering, parsing, and comparison helpers.
- `test_statistics_tools.py`: deterministic statistics helpers.
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
pytest -q
python -m compileall src tests
python -c "import yaml; yaml.safe_load(open('configs/models.yaml')); yaml.safe_load(open('configs/agents.yaml')); yaml.safe_load(open('configs/tools.yaml'))"
```

Use a CLI smoke test after changing commands:

```bash
PYTHONPATH=src python -m hackathon_agents.cli --help
```
