# LaTeX Paper Workspace

This folder is for drafting the paper that comes out of the agent workflow.

## Files

- `main.tex`: paper skeleton and section structure.
- `references.bib`: BibTeX database for cited work.
- `Makefile`: convenience build target for local TeX installations.

## Build

```bash
cd latex
make
```

The build expects `latexmk` and `pdflatex` to be installed. The agent workflow can also generate run-specific LaTeX reports under `runs/<timestamp>/report.tex` without requiring a TeX installation.
