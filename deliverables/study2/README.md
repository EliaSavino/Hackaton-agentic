# ADC Linker Design — Study 2 (revised): payload-class-aware design

Extends Study 1 to answer a chemist's critique: the scorer was implicitly built for
**cytotoxin** delivery, but modern antibody conjugates carry **non-traditional payloads**
(oligonucleotides, immunomodulators) whose linker requirements *invert*. A single agent now
reads the literature per payload class and designs correctly for all three.

| File | What it is |
|------|-----------|
| `ADC_Linker_Study2_Paper.pdf` | **Main paper, 5 pages** — payload-aware controlled grid, benchmark, calibration, Boltz affinity proof |
| `ADC_Linker_Study2_Supplementary.pdf` | Supplementary, 4 pages — full 38-context table, payload re-scoring table, novelty, calibration, commercial + Boltz panels |
| `adc_linker_study2.tex`, `_supp.tex` | LaTeX sources |
| `figures/` | conjugation heatmap, **payload-flip**, Pareto, novelty, Boltz, per-context bars |
| `grid_results.json` | 76 runs (38 contexts × 2 seeds), all designed linkers + scores |
| `benchmark.json` | commercial linkers + independent yardsticks + calibration |
| `boltz.json` | cathepsin-B co-folding metrics (designed + negative control + commercial) |
| `PLAN_STUDY2.md` | the revised plan and rationale |

## Design (why it is credible)

- **Payload-class-aware scoring.** Three literature-grounded rules — cytotoxin (reward
  cleavable, bystander effect), oligonucleotide/ARC (**penalise cleavable → favour rigid
  non-cleavable sulfo-SMCC**), immunomodulator/ISAC (cleavable permitted but **plasma
  stability paramount**) — each compiled deterministically onto a **fixed** six-objective
  scorer. The agentic literature step is LLM-derived with an API key, else literature-encoded
  (this run: encoded, with citations).
- **Controlled experiment.** 8 conjugation chemistries (incl. the new **tetrazine/TCO IEDDA**
  pair) × payload-conditioned trigger panels × 2 seeds = **76 real REINVENT runs, 0 failures**.
  Objective *dimensions* held fixed; only the payload rule, warhead context and seed vary.
  Seed variance is tiny (SD 0.0001–0.038).
- **Non-circular evaluation.** QED/physchem/Morgan-novelty yardsticks the optimiser never saw,
  a stability-surrogate calibration, and a **Boltz-2** structural proof point.

## Headline results

- **The payload rule re-scores the same context.** Holding handle+trigger fixed, the
  protease-cleavable context is penalised under the oligonucleotide rule: e.g.
  **Maleimide/Val-Cit 0.70 (cytotoxin) → 0.45 (oligonucleotide)**, a ~36% collapse, so the
  non-cleavable caps (rigid sulfo-SMCC 0.76, flexible 0.78) become the optimum — reproducing
  the ARC design principle that a cleavable linker is a liability for oligonucleotide cargo.
  For cytotoxins both cleavable and non-cleavable are admissible; the immunomodulator rule
  up-weights plasma stability.
- **The two IEDDA handles integrate cleanly.** Tetrazine/Non-cleavable = 0.82, competitive
  with the best established chemistries; the conjugation ranking from Study 1 survives.
- **Honest limit:** the compact non-cleavable cap wins on pure drug-likeness under *every*
  payload rule (physicochemistry dominates), so we do **not** claim "cleavable wins for
  cytotoxins." The demonstrable result is the payload-dependent *re-scoring* of cleavable
  linkers, strongest (and unambiguous) for oligonucleotides.
- **Boltz-2 (affinity, not ipTM).** Interface confidence is uniformly high (ipTM 0.77–0.91:
  everything docks), so it does not discriminate. **Predicted binding affinity does:** designed
  protease-cleavable linkers reach **Kd 6–76 nM** (best Maleimide/Val-Cit, 6 nM), bracketing
  the clinical **mc-Val-Cit substrate (43 nM)**; the oligonucleotide-optimal **non-cleavable
  negative control binds ~15× weaker (787 nM)**, and non-substrate spacers (maleimidocaproyl,
  acid-labile hydrazone) bind in the **micromolar** range. Affinity tracks cleavability.

## Reproduce

```bash
# clean pod orphans, then the payload-aware grid (detached, resumable; 2 seeds, workers=5)
ssh pod 'pkill -9 -f reinvent || true'
python -c "from hackathon_agents.demos.adc_study2 import run_study2_grid; run_study2_grid(resume_dir='runs/grid_war3')"
python -c "from hackathon_agents.demos.adc_study import finalize_study; finalize_study('runs/grid_war3/grid.json')"
```
See `../../HANDOFF.md` (ROUND 3) for the shared-pod concurrency discipline and the honesty guard.
