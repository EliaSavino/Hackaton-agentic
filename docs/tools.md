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
