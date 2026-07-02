# Study 4 — The Reasoning Scientist (Visible · Validated · Uncertainty-Aware · Actionable)

Study 4 answers `CRITIQUE_S3.md`. Study 3 built the machinery of an autonomous scientist;
the reviewer's verdict was that the paper *demonstrated a workflow* but did not yet *prove
the workflow reasons*. Study 4 makes the reasoning **visible**, **validated on held-out
literature**, **uncertainty-aware**, and **actionable** — and reframes the contribution as
an autonomous medicinal-chemistry scientist, with ADC linker design as the application.

## The root-cause fix that unblocked everything

Across Studies 2–3, **every** agent LLM call silently failed and fell back to *hardcoded*
rules — the exact source of the reviewer's recurring "rules were literature-encoded, not
LLM-derived" complaint. Cause: `configs/models.yaml` pinned `anthropic/claude-opus-4.6`
(a dot), an invalid model ID; the Anthropic API returns *"model: claude-opus-4.6 was not
found. Did you mean claude-opus-4-6?"* and the code fell back. Fixed to `claude-opus-4-6`.
Study 4 is the first iteration whose reasoning is **genuinely LLM-driven**.

## Headline results

| Deliverable | What it shows | Critique point |
|---|---|---|
| `ADC_Linker_Study4_Paper.pdf` (5 pp) | Autonomous scientist: visible reasoning + held-out prediction + actionable designs | overall |
| `ADC_Linker_Study4_Supplementary.pdf` (7 pp) | Full reasoning chains, held-out detail, 15 dossiers, Boltz co-folds | — |
| `figures/fig_reasoning_cascade.png` | The reasoning chain per class: retrieval → grounded exemplars → rule (+confidence) → objective | #1 |
| `figures/fig_heldout.png` | Leave-one-paper-out: confidence **collapses 0.80→0.01** when the oligo class's sole ARC paper is withheld, point prediction stays correct | #2, #3, #6 |
| `figures/structure_gallery.png` + `struct_*.png` | Drawn designs: handle (blue) / scissile bond (red) / solubiliser (green) | structures |
| `dossiers.json` | 15 candidate dossiers (route, cost, P(success), failure modes, validation) — all 15 LLM-authored | #4, #8 |
| `boltz_whole_conjugate.json` | Whole-conjugate (linker + real payload) co-fold vs cathepsin B | #9, #5 |

### The central experiment (leave-one-paper-out)
- **Cytotoxin** (withhold 1 of 4 papers): predicts cleavable ✓, confidence 0.76→0.84 (robust).
- **Immunomodulator** (withhold 1 of 2): predicts cleavable ✓, confidence 0.64→0.67 (robust).
- **Oligonucleotide** (withhold its *only* ARC paper): still predicts non-cleavable ✓ **but
  confidence collapses 0.80→0.01** — the extractor returns *zero* exemplars (refuses to invent
  evidence), the agent states it is speculating, and it *misses* the paper-specific "rigid >
  flexible" insight. Calibrated uncertainty: the agent knows what it doesn't know, and flags
  exactly where more literature is needed.

### Independent (non-encoded) reasoning
The LLM-derived **immunomodulator** rule *diverges* from the hand-encoded prior (it derived a
cleavage preference from ISAC potency data rather than replaying "stability paramount"),
demonstrating the conclusions originate in the literature analysis, not the scorer's construction.

### Whole-conjugate Boltz-2 (honest framing)
All conjugates co-fold into the cathepsin-B cleft (ipTM 0.75–0.93). Predicted Kd: clinical
mc-Val-Cit-PABC+MMAE 45 nM, ISAC 43 nM, ARC 74 nM, disulfide cytotoxin 1199 nM. Affinity
tracks **shape complementarity / recognition, not cleavability** (only the redox disulfide —
which cathepsin B, a protease not a reductase, cannot process — is weak). Framed as substrate
recognition, never as proof of cleavage.

## How to reproduce
```bash
PY=/Users/es/miniforge3/envs/hackathon-agents/bin/python
export PYTHONPATH=src
$PY -m hackathon_agents.demos.adc_study4 1          # Phase 1: reasoning chains
$PY -m hackathon_agents.demos.adc_study4 2          # Phase 2: leave-one-paper-out
$PY -m hackathon_agents.tools.adc_shortlist          # rule-matched shortlist
$PY -m hackathon_agents.tools.draw_linker_constructs # structure gallery
$PY -m hackathon_agents.tools.adc_dossier            # dossiers (LLM)
$PY -c "from hackathon_agents.config import load_config; load_config(env_file='.env'); \
        from hackathon_agents.demos.adc_study4_boltz import run_whole_conjugate_panel; run_whole_conjugate_panel()"
$PY -m hackathon_agents.tools.adc_study4_figures     # figures
$PY -m hackathon_agents.tools.adc_study4_paper       # build + compile PDFs
```

## Open dependency (literature)
The oligonucleotide held-out is the showcase but the corpus has only **one** ARC paper, so
the correct prediction comes at ~0 confidence. Adding 2–3 more ARC / antibody–oligonucleotide
papers (and 1–2 ISAC) would turn it into a *confident* recovery of the rigid non-cleavable
rule from independent papers — the strongest form of the central experiment. See `PLAN_STUDY4.md` §12.
