# Study 5 — Closing the Loop, Honestly (answers Reviewer 2, Part IV)

Study 4 was "the first iteration [the reviewer] would let out of the building" — fabrications
gone, reasoning genuinely visible and validated. Reviewer 2's Part IV listed the remaining gaps.
Study 5 closes them.

## What changed vs Study 4 (by reviewer point)

| Point | Study 4 gap | Study 5 fix |
|---|---|---|
| **IV.1** | Shortlist *selected* from a cached pre-Study-4 pool; derived rule didn't *generate* | **The compiled objective now generates the molecules.** Per class: derived rule → `ADCGoalProfile` → `build_adc_linkinvent_objective` → REINVENT4 LinkInvent (pod, real, `mock=False`). 15 designs, each carrying the derived motif (Val-Cit / Val-Ala / rigid sulfo-SMCC cap) |
| **IV.2** | "Whole-conjugate" Boltz was a disconnected mixture | Reframed honestly as **linker + payload co-present** in the pocket (two ligands), a recognition/plausibility check — not a covalent conjugate, not cleavage |
| **IV.3** | Synthesizability = discretized step-count heuristic; a real SA_Score was computed then discarded | **Continuous Ertl SA_Score** (the same metric the generator optimises) is now the scoring axis; the step-count survives only as a reported **complexity index** (never a hard gate) |
| **IV.4** | Concern that `self_confidence` 0.55 was a default | Confirmed **real, varied LLM output** (0.72/0.55/0.60); labelled "LLM self-report" in provenance |
| **IV.5** | Oligo held-out was calibration (collapse to ~0), not recovery | With the enriched corpus, the held-out **discriminates**: cytotoxin/ISAC rules recover robustly (0.96, 0.83); the **ARC rule is contested** (see below) |
| **IV.6** | No provenance gate in code | **Provenance gate** (`tools/provenance.py`): every value tagged measured/llm/heuristic; the paper builder **refuses any mock constant into a result** and prints a provenance table in the SI |

## The headline honest finding (IV.5)

With the corpus grown 8 → **31 papers**, the leave-one-paper-out test does more than confirm — it
**discriminates robust rules from a contested one**:

- **Cytotoxin** (withhold 1 of ~5): recovers *cleavable Val-Cit* at confidence **0.96**.
- **ISAC** (withhold 1 of ~4): recovers *cleavable + high-stability* at **0.83**.
- **ARC / oligonucleotide** (withhold the siRNA showcase paper): the agent confidently derives the
  **opposite** rule — *protease-cleavable Val-Cit*, confidence **0.81**, 9 grounded exemplars — from
  the **modern clinical antibody-oligonucleotide-conjugate literature (DYNE-101/251, AOC-1001)**.

That is the honest state of the science: early cationic-assistance-free siRNA conjugates favour a
rigid **non**-cleavable sulfo-SMCC linker, while clinical AOCs increasingly use **cleavable** Val-Cit.
A lookup-table agent would have hidden this; ours surfaces it, and its confidence tracks the evidence
it is given — the strongest evidence yet that the conclusions are literature-derived, not encoded.
(Exactly the caution Reviewer 2 raised in IV.5, now demonstrated empirically.)

## Structural coherence (Boltz-2, cathepsin B)

The rule-generated designs behave correctly in the co-fold: the **Val-Cit cytotoxin design binds
tightest (Kd 8.9 nM)**, near the clinical mc-Val-Cit-PABC control (35 nM), while the **rigid
non-cleavable ARC design binds weakest (109 nM)** — predicted affinity tracks cathepsin-B substrate
compatibility (recognition, not cleavage).

## Files
- `ADC_Linker_Study5_Paper.pdf` (5 pp), `ADC_Linker_Study5_Supplementary.pdf` (6 pp)
- `generated_designs.json` — REINVENT output per class (real, `mock=False`)
- `reasoning_chains.json`, `heldout_predictions.json`, `shortlist.json`, `dossiers.json` (15/15 LLM), `boltz.json`
- `figures/` — reasoning cascade, held-out (robust-vs-contested), structure gallery
- Provenance table: SI §1 of the supplementary.

## Reproduce
```bash
PY=/Users/es/miniforge3/envs/hackathon-agents/bin/python; export PYTHONPATH=src
HACKATHON_AGENT_LLM_MODE=always $PY -m hackathon_agents.demos.adc_study5_generate     # reason→generate (pod)
HACKATHON_AGENT_LLM_MODE=always $PY -m hackathon_agents.demos.adc_study5_heldout      # held-out
$PY -c "from hackathon_agents.tools.adc_shortlist import write_shortlist_from_generated as w; w()"
$PY -c "from hackathon_agents.tools.draw_linker_constructs import render_gallery as g; g('deliverables/study5/shortlist.json','deliverables/study5/figures')"
$PY -c "from hackathon_agents.tools.adc_dossier import run_dossiers as r; r('deliverables/study5/shortlist.json','deliverables/study5/reasoning_chains.json','deliverables/study5/dossiers.json')"
$PY -c "from hackathon_agents.config import load_config; load_config(env_file='.env'); from hackathon_agents.demos.adc_study4_boltz import run_whole_conjugate_panel as b; b('deliverables/study5/shortlist.json','deliverables/study5/boltz.json')"
$PY -c "from hackathon_agents.tools.adc_study4_figures import render_study5_figures as f; f()"
$PY -m hackathon_agents.tools.adc_study5_paper
```
