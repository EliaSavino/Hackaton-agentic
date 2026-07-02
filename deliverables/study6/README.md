# Study 6 — Publishable revision (Reviewer 2, Parts V.1, VI & VII)

Reviewer 2's Part V called Study 5 *"publishable-grade on the honesty axis"* and asked for
one real fix (V.1) plus a writing/figures pass (VI/VII, no new data). This is that revision.
**No experiments were re-run** — every figure and number derives from the Study-5 JSON in
`deliverables/study5/`.

## What changed

**V.1 — confidence is now disagreement-aware (the one substantive fix).** The old confidence
rewarded evidence *volume*; the ARC held-out scored 0.81 even though its exemplars split. New
metric (`tools/consensus.py`): confidence is high only when the grounded exemplars are both
plentiful *and* consistent, and a split flags `contested`. Result:

| Class | Held-out evidence | New held-out confidence | vs old |
|---|---|---|---|
| Cytotoxin | 8 cleavable / 0 → unanimous | **0.97** (robust) | ~same |
| ISAC | 1 cleavable / 0 → unanimous | **0.83** (robust) | ~same |
| **ARC** | **4 cleavable / 2 non-cleavable → contested** | **0.33** (flips + collapses) | 0.81 → 0.33 |

"Contested" is now a *computed, calibrated output*, not a caption — exactly what V.1 asked for.

**Part VI — the paper now reads as a paper.**
- One-line title (was a three-line sentence-subtitle).
- Five-sentence abstract that **leads with the contested-ARC finding**.
- **AI tools ("Claude", "J.A.R.V.I.S") removed from the author list** → an *AI-tools statement*
  in Acknowledgements (ICMJE/Nature/ACS compliance; this was a desk-reject blocker).
- The word "honest" (6× in Study 5, incl. a section title) → **0×**; honesty is shown by the SI
  provenance table, not asserted.
- Full-corpus vs held-out confidence labelled everywhere; "direction flips" wording; self-references
  to prior iterations removed.
- Tables: 3-row representative shortlist in the main text (full 15 → SI); P(success) moved to SI
  with the peptide-penalty caveat stated; readable citations instead of filename slugs.

**Part VII — new 4-figure narrative spine** (`tools/adc_study6_figures.py`):
1. **Fig 1 — journey**: one cytotoxin molecule from a real retrieved quote → grounded exemplar →
   derived rule → *drawn generated structure* → cathepsin-B Kd. The whole thesis in one strip.
2. **Fig 2 — the money figure**: held-out confidence (robust green vs contested red) *plus* the
   evidence-composition strip that explains it (ARC 4:2 = contested; others unanimous).
3. **Fig 3 — rules steer chemistry**: objective-weight heatmap + the 75 generated designs
   separating by class along the two rule knobs (rotatable bonds; cleavable-motif presence).
4. **Fig 4 — co-fold recognition**: Kd dot plot (Val-Cit 9 nM ≈ clinical 35 nM ≪ rigid ARC 109 nM).

Also: scissile-bond SMARTS tightened (red marks the Cit-PABC anilide, not every carbonyl);
`boltz.json` flag renamed `whole_conjugate` → `co_present`; gallery label "steps" → "cplx idx".

## Files
- `ADC_Linker_Study6_Paper.pdf` (5 pp) · `ADC_Linker_Study6_Supplementary.pdf` (6 pp)
- `figures/` — fig1_journey, fig2_heldout, fig3_rules_steer, fig4_cofold, structure_gallery
- Data JSONs live in `deliverables/study5/` (unchanged; this is a revision, not a re-run).

## Reproduce (no pod, no LLM re-runs)
```bash
PY=/Users/es/miniforge3/envs/hackathon-agents/bin/python; export PYTHONPATH=src
$PY -m hackathon_agents.tools.adc_study6_figures      # 4 figures from study5 JSON
$PY -m hackathon_agents.tools.adc_study6_paper        # build + compile PDFs
```

## Standing (deferred, named in the paper as boundaries)
Real retrosynthesis (AiZynthFinder, n=15); covalent Boltz conjugate; deeper generative sampling
(>25/class); conjugate-level biological realism (DAR, Fc, PK).
