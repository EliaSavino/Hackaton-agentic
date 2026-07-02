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
- `ADC_Linker_Study6_Paper.pdf` (**5 pp**) · `ADC_Linker_Study6_Supplementary.pdf` (**8 pp**)
- `figures/` — fig1_journey, fig2_heldout, fig3_rules_steer, fig4_cofold, fig5_sensitivity, fig6_gallery
  (fig6 is now rendered in the **SI**, not the main text — see Part XI)
- Data JSONs live in `deliverables/study5/` (the ISAC objective was corrected in place by the V7
  safety gate; molecules are the same real REINVENT SMILES, re-scored under the gated objective).

## Reproduce (no pod, no LLM re-runs)
```bash
PY=/Users/es/miniforge3/envs/hackathon-agents/bin/python; export PYTHONPATH=src
$PY -m hackathon_agents.tools.adc_study6_figures      # 4 figures from study5 JSON
$PY -m hackathon_agents.tools.adc_study6_paper        # build + compile PDFs
```

## Part VIII — the headline is now a falsifiable hypothesis (rubric criterion 1)

The reviewer's last note: the honesty and figures are done; the highest-leverage move for the
*novelty* rubric is to promote the contested-ARC observation into an explicit, falsifiable
**hypothesis** and lead with it. Done — and we didn't just assert it, we **tested it in silico**:

> **Hypothesis (agent-derived, falsifiable):** for antibody–oligonucleotide conjugates, a
> protease-cleavable Val-Cit linker matches or outperforms the rigid non-cleavable sulfo-SMCC
> standard on protease-mediated payload release.

- **Derived** by the agent from the clinical AOC literature (the held-out ARC rule, siRNA paper withheld).
- **Generated**: a Val-Cit ARC linker under that rule (REINVENT, real, `mock=False`) — see
  `hypothesis_arc.json` / `reinvent_runs_hypothesis/`.
- **Tested**: it co-folds with cathepsin B at predicted **Kd 9.7 nM** — as tightly as the clinical
  Val-Cit substrate (35 nM) and the cytotoxin Val-Cit design (9 nM), while the rigid non-cleavable
  ARC design binds **11× weaker (109 nM)**. In-silico feasibility support for the prediction.
- **Falsifiable**: a wet-lab comparison of Val-Cit vs sulfo-SMCC ARC linkers on protease-mediated
  release / potency would confirm or refute it. Stated in the paper.

The abstract now leads with this prediction; the meta-contribution (an agent whose confidence
tracks literature consensus) is the secondary novelty. Also fixed per Part VIII: the
full-corpus vs held-out confidence gap (e.g. cytotoxin 0.60 vs 0.97) is now explained in the
Discussion; Fig 4 labels humanised + the hypothesis point added; Fig 1 citation unified
("Balamkundu 2023"); Fig 2 y-axis capped; Fig 3 caption corrected to "rigidity knob".

## Part IX & X — Version 7 (independent-reviewer fixes + a substantive weight correction)

- **IX.4 (substantive) — the ISAC stability weight was backwards.** The LLM derived only a
  *standard* plasma-stability priority for the immunomodulator (ISAC) class from **zero
  stability-labelled exemplars** (self-confidence 0.25), compiling to the **lowest** stability
  weight of the three classes (0.70) — wrong for a TLR7/8 agonist, whose premature systemic
  release drives cytokine-release syndrome. A **low-evidence safety gate** now sits in the
  compiler (`lit_reasoning_s4.compile_objective`): when a class states fewer than three grounded
  plasma-stability exemplars, the stability weight is floored to the **encoded domain prior**
  (paramount ≈ 1.0 for ISAC), never lowered. It fires only for ISAC (0.70 → **1.00**); cytotoxin
  and oligo are unchanged. The raw LLM rule (`standard`) is preserved as honest provenance; the
  gate override is documented in the SI. The ISAC shortlist is the same real REINVENT molecules,
  re-scored under the gated objective (ranking unchanged — the stability subscore is uniform).
- **X.1 — every confidence is now arithmetic-checkable.** Table 1 gained an `n (c/n)` column
  (cyto `8 (8/0)`, ISAC `5 (1/0)`, ARC `9 (4/2)`), and the caption shows the derivation, so a
  juror can compute `C = min(1,n/6)·max(0,2κ−1)` for every row (e.g. ISAC 5(1/0) → 0.83).
- **X.2** — one sentence states ISAC's 0.83 rides on evidence *volume*, not tested consensus
  (a single cleavage-labelled exemplar cannot be flagged contested), so it is a lower bound.
- **X.3** — count slips reconciled: "31 papers" → **30** everywhere; "25 designs/class" → "25
  generated per class → 15 shortlisted (5/class)".
- **IX.1–IX.3 (Fig 3)** — the "flexibility" heatmap column is renamed **rigidity (low-rot reward)**;
  the per-class rotatable-bond setpoint (rot≤5/10/14) is exposed as the real separator; the scatter
  y-axis now carries a real quantity (Ertl SA subscore) instead of decorative jitter; the weights
  are labelled a deterministic rule-compilation (heuristic, ~3 buckets), and "two rule knobs" →
  "driven mainly by the rigidity knob".
- **New Fig 6 — trial-molecule gallery** (personal request): two real generated linkers per class,
  each carrying its literature-derived motif by construction, with SMARTS-detected highlights.

## Part XI — Cosmetic pass (purely stylistic; no number or claim changed)

A layout/beauty pass. **Nothing here changes a value or a result** — same JSON, same figures'
data, re-rendered and re-typeset only.

- **XI.0 — back under the 5-page limit.** The 6th page held only Fig 6 (gallery) plus three
  trailing references. Fig 6 moved to the **SI** (it is redundant with Table 2 and Fig 1's inset),
  in-plot suptitles were dropped in favour of the LaTeX captions, and the float↔text spacing was
  tightened. Result: a clean **5-page** main text (4-figure spine: journey, held-out, rules-steer,
  co-fold), SI now 8 pp.
- **XI.1 — one semantic colour language across every figure:** cleavable = teal (`#2C7FB8`),
  rigid/non-cleavable = amber (`#E6820E`), contested/flips = red, robust/recovers = green (outcome
  accents), clinical/neutral = slate. The two cleavable classes share the cool teal family, the
  rigid/contested ARC class is amber, so "cleavable vs rigid" reads in the same ink everywhere.
- **XI.2 — title** dropped to 16/19 pt (via `anyfontsize`): same words, less shouting, more air.
- **XI.3 — per-figure polish.** Fig 1: neutral slate boxes with a teal accent only on the two
  stages the agent produces (DERIVED RULE, GENERATED) + a legible "generated Val-Cit design"
  caption. Fig 2 (money): full-corpus bars muted to neutral grey so the green-recover/red-flip
  held-out bars are the only saturated ink, plus a dotted 0.5 contested-floor gridline anchoring
  the ARC flip below it. Fig 3: heatmap → `YlGnBu` (legible labels in every cell), scatter
  palette-keyed with a distinct marker per class and the legend tucked inside. Fig 5 (co-fold):
  height cut, markers recoloured by cleavage class (cleavables teal cluster left, rigid ARC amber
  far right, clinical slate), and the bold hypothesis label offset so it no longer collides with
  the markers or the axis ticks. Sensitivity (Fig 4): shortened, palette-aligned bands.
- **XI.4 — typographic nits:** em-dashes and redundant in-plot titles removed (the caption is the
  single voice).

## Standing (deferred, named in the paper as boundaries)
Real retrosynthesis (AiZynthFinder, n=15); covalent Boltz conjugate; deeper generative sampling
(>25/class); conjugate-level biological realism (DAR, Fc, PK).
