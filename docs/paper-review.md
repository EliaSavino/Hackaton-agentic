# Paper Review

The paper-review toolset is deterministic and structured. It is intended for triage, not final scientific judgment.

## Command

```bash
PYTHONPATH=src python -m hackathon_agents.cli review-paper path/to/paper.txt \
  --domain chem_bio \
  --focus-question "Are controls and replicates described?"
```

Optional output path:

```bash
PYTHONPATH=src python -m hackathon_agents.cli review-paper paper.pdf \
  --output runs/my_paper_review.json
```

## Supported Inputs

- `.txt`
- `.md`
- `.pdf`, via `pypdf`
- `.docx`, via `python-docx`

Missing optional packages are returned as structured tool errors.

## Main Functions

```python
from hackathon_agents.tools.paper_review import review_paper

result = review_paper(
    {
        "path": "paper.txt",
        "domain": "chem_bio",
        "focus_questions": ["Does the paper describe controls?"],
        "output_path": "runs/review.json",
    }
)
```

The result is a `ToolResult`.

Important output fields:

- `review.metadata`
- `review.abstract`
- `review.sections`
- `review.claims`
- `review.strengths`
- `review.limitations`
- `review.reproducibility_checklist`
- `review.focus_question_notes`
- `review.recommendation`
- `review.summary`

## Domains

Supported `domain` values:

- `general`
- `chemistry`
- `biology`
- `chem_bio`

Domain changes the reproducibility checklist. For example, `chem_bio` checks both chemical identity signals and biological assay signals.

## Review Depth

Supported `review_depth` values:

- `quick`: fewer claim-like statements.
- `standard`: default.
- `deep`: more claim-like statements.

This is deterministic depth, not model reasoning depth.

## What It Detects

The tool uses heuristics for:

- section headers
- title, year, DOI, and rough authors
- claim-like sentences
- methods and results signals
- controls and baselines
- replicates and sample size
- statistical analysis
- data availability
- code availability
- chemical identity evidence
- yield or conversion
- biological system
- assay conditions
- overclaiming language

## What It Does Not Do

It does not:

- verify citations
- search the internet
- judge novelty against the literature
- deeply understand figures or tables
- validate experimental correctness
- replace expert review

## Future LLM-Assisted Review Pattern

Keep the deterministic review as the first pass. Then use an agent to review the structured output.

Recommended flow:

```text
load paper
  -> deterministic review
  -> paper_reviewer agent validates and expands findings
  -> critic checks overclaiming
  -> writer produces report
```

The LLM should receive:

- abstract or section summaries
- deterministic findings
- evidence snippets
- focus questions

The LLM should not receive:

- unnecessary full text
- huge raw PDFs
- unbounded prior messages

## Batch Review

```python
from hackathon_agents.tools.paper_review import batch_review_papers

result = batch_review_papers(
    ["paper1.txt", "paper2.pdf"],
    output_dir="runs/paper_reviews",
    domain="chem_bio",
)
```

Each successful review can write a JSON artifact.
