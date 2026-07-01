# RUN PLAN — Design-grid sweep + commercial benchmark (in-silico proof points)

Goal: (A) generate optimized linkers across a principled grid of conjugation×trigger
contexts, with seeds; (B) benchmark them against real/commercial linkers on
**independent** yardsticks; (C) tell the honest Pareto/trade-off story. Extends the
existing pipeline; does not replace the 5-page paper (that becomes the "method +
headline result"; this adds the systematic proof-point study).

---

## 0. Experimental design principle (why this is a controlled experiment)

- **Hold the objective FIXED** (same `ADCGoalProfile`, same scoring function) across
  every grid cell. Then any difference between cells is attributable to the *warhead
  context*, not to objective drift. (This is why the grid is REINVENT-only staged-learning,
  NOT the full LLM agent loop — the autonomous-decision story already lives in the 4-pair
  campaign; the grid is the controlled sweep.)
- **Vary two things only:** the warhead pair (context) and the RNG **seed** (replicate).
- **Two molecule sets:** Set A = our designed linkers; Set B = real/commercial linkers.
- **Judge on metrics the RL did NOT optimize** (see §3) so "better/worse" is not circular.

---

## 1. The grid — and why exactly these cells (the convincing part)

Two axes = the two design levers the problem statement names: "robust conjugation
chemistries" × "tunable cleavage triggers." Selection is **data-driven then
chemistry-filtered**, not arbitrary.

### 1a. Conjugation handles — 6 of 10

Library A frequency (data) and the filter applied:

| Handle | Lib A count | Conjugation biology | Verdict |
|---|---|---|---|
| Maleimide | 83 | Cys thiol-Michael | **KEEP** — clinical workhorse; carries the retro-Michael liability we want to test against |
| DBCO | 131 | Copper-free click (SPAAC) | **KEEP** — most frequent click handle; site-specific, homogeneous DAR |
| Oxyamine | 79 | Aldehyde-tag / HIPS oxime | **KEEP** — enzymatic site-specific bioconjugation; stable oxime |
| Pyridyl-disulfide | 6 | Disulfide exchange (redox) | **KEEP** — redox-tunable, steric-shielding story |
| NHS-ester | 7 | Lys amide coupling | **KEEP** — non-Cys route; broadens antibody/payload compatibility |
| Bromoacetamide | 3 | Cys alkylation (irreversible) | **KEEP** — the *stable* alternative to maleimide (no retro-Michael) — a direct hypothesis test |
| Azide | 213 | click partner | drop — bare `[N3]`, not a standalone antibody end; represented by DBCO |
| Alkyne | 151 | click partner | drop — bare `C#C`; represented by DBCO |
| Aldehyde | 25 | oxime partner | drop — pairs with Oxyamine, which we keep as the stable handle |
| BCN | 1 | click | drop — redundant with DBCO, n=1 |

Rationale in one line: **rank by empirical frequency, keep only groups that are a
chemically valid standalone antibody-conjugation warhead, and span the distinct
conjugation biologies (Cys-reversible, Cys-irreversible, Lys, click, redox, enzymatic).**
The two most frequent entries (azide/alkyne) are deliberately dropped *with reason* — they
are click *partners*, not antibody ends, and DBCO already represents copper-free click.

### 1b. Cleavable triggers — 4

| Trigger | Source | Mechanism | Why |
|---|---|---|---|
| Val-Cit-PABC | Library B (n=13) | lysosomal protease | Canonical; most clinically prevalent (its data dominance mirrors real ADCs) |
| Val-Ala-PABC | Library B (n=2) | lysosomal protease | Stability-tuned variant — tunability demo (already our current winner) |
| Glucuronide | corpus SMILES | β-glucuronidase | Mechanistically distinct + intrinsically hydrophilic (solubility angle) |
| Non-cleavable stub | control | none (Ab catabolism) | Control: does the agent design differently when no cleavage is required? |

**Deliberately excluded from the design axis: hydrazone (acid-labile) and standalone
disulfide triggers.** Our objective *penalizes* acid-labile motifs and treats plasma
stability as a hard filter — designing *toward* a hydrazone contradicts the objective.
Instead these appear in **Set B (commercial benchmark)**, where the point is to show our
scorer correctly ranks them as less plasma-stable (§3 calibration). Clean A→B bridge.

### 1c. Grid = 6 × 4 = **24 contexts** × **3 seeds** = **72 REINVENT runs**

Each warhead is annotated with one LinkInvent attachment point (`w1(*)|w2(*)`), RDKit-
validated (exactly one dummy atom). Attachment SMILES are defined once in
`demos/adc_grid.py`.

---

## 2. Set B — the commercial / literature baseline

Assemble ~10–15 real clinical/commercial linkers (canonical SMILES + from `data/linkers.csv`
product names), scored identically. Minimum set:
- MC-Val-Cit-PABC (Adcetris / brentuximab vedotin)
- MC-Val-Ala-PABC
- SMCC / MCC — non-cleavable thioether (Kadcyla / T-DM1)
- SPDB / sulfo-SPDB — hindered disulfide (Elahere / mirvetuximab)
- Hydrazone linker (Mylotarg / gemtuzumab)
- β-glucuronide linker
- maleimidocaproyl (mc) alone; MC-GGFG (Enhertu-style) if available in the CSV

---

## 3. Yardsticks (independent unless noted)

1. **Composite ADC score** — the trained objective. Reported but flagged *in-sample*.
2. **QED** (RDKit) — drug-likeness, **not** in the objective → independent.
3. **Fraction sp3, aromatic-ring count, HBD/HBA, TPSA, cLogP/logD** — physicochemical
   spread; mostly independent (solubility subscore uses logP/TPSA, so report these raw as
   distributions, not as the win metric).
4. **Aggregation/hydrophobicity proxy** — e.g. calculated logD + aromatic proportion
   (a known aggregation risk factor for ADCs) → independent.
5. **Synthetic accessibility (SA)** — IS in the objective; this is the honest **trade-off
   axis** (our RL linkers scored poorly here). Report, don't spin.
6. **Novelty** — Morgan-FP Tanimoto of each designed linker to nearest neighbour in Set B.
   Low = novel chemotype; high = rediscovery.
7. **Scorer calibration table** — score the known clinical classes and show the stability
   subscore reproduces the literature ordering
   (hydrazone < disulfide < Val-Cit ≈ non-cleavable). This *validates the surrogate* and
   earns the right to use it comparatively. **This is the credibility linchpin.**
8. *(Optional / stretch)* **Boltz-2 structural proof point** — only if a working GPU pod
   appears; current pod GPU is dead (driver mismatch) and CPU Boltz is too slow. Not on the
   critical path.

---

## 4. Parallelization on the pod

- Pod = 192 cores, ample RAM (confirmed). Each REINVENT is thread-capped to 16.
- Run **~10 concurrent** REINVENT jobs (10 × 16 = 160 threads, headroom left) via a local
  `ThreadPoolExecutor(max_workers=10)` firing `generate_with_reinvent` calls — reuses the
  existing, tested SSH path. Each job gets a **unique remote workdir + unique seed**.
- **Phase-0 must verify** remote-workdir uniqueness (grep `_generate_with_reinvent_ssh`);
  if the remote dir isn't per-job-unique, add a job-id/seed suffix so concurrent jobs don't
  clobber each other's config/output on the pod.
- Est. wall time: 72 runs ÷ 10 concurrent ≈ 8 waves × ~4 min (60 steps, fragment scoring)
  ≈ **~30–40 min** for the whole grid.

---

## 5. Pipeline (phases → steps → artifacts)

**Phase 0 — Prep & validation (local + 1 pod smoke, ~10 min)**
- Verify remote-workdir uniqueness for concurrent SSH runs; patch if needed.
- Define grid + attachment SMILES in `demos/adc_grid.py`; RDKit-validate all 6+4 warheads.
- 1 fast concurrent smoke: 2 contexts × 1 seed, 10 steps, confirm no collision + real output.

**Phase 1 — Grid sweep (pod, parallel, ~40 min)**
- `demos/adc_grid.py::run_grid()` → 72 concurrent staged-learning runs, fixed objective.
- Writes `runs/grid_<ts>/grid.json`: per (context, seed) → run dir, top assembled linkers
  (RDKit trigger-filtered), scores + all descriptors.

**Phase 2 — Score Set A + Set B on all yardsticks (local, RDKit, minutes)**
- `tools/linker_benchmark.py`: canonical commercial SMILES + `score_adc_linker` + QED +
  physchem + SA + Morgan-Tanimoto novelty. Emits `benchmark.json`.

**Phase 3 — Calibration (local, minutes)**
- Score known clinical classes; build the stability-ordering calibration table; assert it
  matches literature (fail loudly if the surrogate is miscalibrated → we'd re-tune before claiming anything).

**Phase 4 — Analysis + figures (local)**
- Grid: heatmap (best composite per context) + violin/box per context across seeds
  (**error bars from seeds**) + seed-variance summary.
- A-vs-B: per-objective distributions; **Pareto front** (solubility vs SA, stability vs SA)
  with designed + commercial points; novelty histogram; calibration table.

**Phase 5 — Paper (local, pdflatex)**
- Extend `tools/adc_campaign_paper.py` (or new `adc_benchmark_paper.py`): add Grid-analysis
  and Benchmark sections + the new figures + calibration table. Keep the main narrative ~5
  pages; push the full 24-cell tables + per-context detail to a **Supplementary** section/
  appendix so the headline stays tight.

---

## 6. New/changed code artifacts

- **new** `src/hackathon_agents/demos/adc_grid.py` — grid definition (+ justification
  metadata), `run_grid()` with `ThreadPoolExecutor` parallel pod sweep, seed handling.
- **new** `src/hackathon_agents/tools/linker_benchmark.py` — commercial set, yardsticks,
  novelty, calibration.
- **extend** `src/hackathon_agents/tools/adc_campaign_paper.py` — grid + benchmark sections
  & figures (or a sibling module + a supplementary).
- **maybe patch** `tools/reinvent_tools.py::_generate_with_reinvent_ssh` — per-job unique
  remote workdir (only if Phase 0 shows it's needed).
- **tests** — extend `tests/test_adc_campaign.py`: grid warheads valid; benchmark scorer
  runs; novelty in [0,1]; calibration ordering holds.

---

## 7. Compute / time budget

| Phase | Where | Wall time |
|---|---|---|
| 0 prep + smoke | local + pod | ~10 min |
| 1 grid (72 runs, 10-wide) | pod | ~30–40 min |
| 2–4 scoring/analysis/figs | local | ~10 min |
| 5 paper + compile | local | ~5 min |
| **Total** | | **~1–1.5 hr** |

---

## 8. The thesis (what we will and won't claim)

WILL: "An autonomous agent produces linkers that are **Pareto-competitive with clinical
linkers** on solubility and plasma-stability-alert-freedom, span diverse conjugation
chemistries, and are validated by a surrogate that reproduces known stability rankings."

WON'T: "our linkers beat everything." Expected honest finding — **we win on
solubility/stability, commercial linkers win on synthesizability**; that trade-off is the
result, and it motivates upweighting SA / adding a real synthesis score next.

---

## 9. Open decisions (small)

1. Paper: single expanded paper (~7–8 pp) **or** 5-pp main + supplementary? (Plan assumes
   the latter.)
2. Boltz structural proof point: leave as optional stretch (needs a working GPU pod)? (Plan
   assumes yes — off critical path.)
3. Seeds: 3 (plan default). Bump to 5 if we want tighter error bars and the pod is free.
