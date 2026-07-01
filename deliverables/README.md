# ADC Linker Design — Deliverables

Autonomous agentic design of next-generation antibody–drug conjugate (ADC) linkers,
solving `data/problemprompt.txt` ("Design a Novel Linker Chemistry with in-silico proof points").

## Contents

| File | What it is |
|------|-----------|
| `ADC_Linker_Design_Paper.pdf` | **The paper** — 5-page, publication-ready manuscript (real data, figures, tables, references) |
| `ADC_Linker_Design_Paper.tex` | LaTeX source of the paper |
| `figures/` | Publication figures (per-pair scores, objective heatmap, property landscape) |
| `campaign_results.json` | Full campaign results: 200 assembled linkers, per-pair decision trails, pooled ranking |
| `Library_A_Antibody_Ends.csv` | 699 conjugation warheads distilled from the reagent corpus |
| `Library_B_Payload_Triggers.csv` | 16 cleavable self-immolative triggers |

## How it was produced

1. **Literature** — 4 ADC-linker reviews ingested into the RAG store (`data/rag.sqlite`).
2. **Warhead libraries** — `tools/generate_linker_libraries.py` distils conjugation
   handles (Library A) and protease-cleavable triggers (Library B) from ~3,700 reagents.
3. **Generative design** — REINVENT4 LinkInvent designs the tunable spacer between a
   conjugation handle and a cleavable trigger, run once per warhead pair across four
   conjugation chemistries (maleimide/cysteine, DBCO/click, pyridyl-disulfide/redox,
   Val-Ala variant). A critic agent scores each linker and autonomously escalates
   sampling → reinforcement learning and re-weights the objective.
4. **Paper** — `tools/adc_campaign_paper.py` aggregates the assembled linkers and writes
   the manuscript + figures.

## Reproduce

```bash
# one command: campaign (real REINVENT on the pod) -> re-aggregate -> paper -> PDF
python -m hackathon_agents.cli design-adc-campaign --run --device cpu

# a single warhead pair (faster):
python -m hackathon_agents.cli design-adc-linkers --run --device cpu \
  --warhead-pair "O=C1C=CC(=O)N1*|CC(C)[C@@H](C(=O)N[C@@H](C)C(=O)Nc1ccc(CO)cc1)N*"
```

## Key result

Across 4 conjugation chemistries the loop produced **200 assembled linkers**; the best
(a maleimide–Val-Ala-PABC design) reached a composite score of **0.78**, combining high
predicted solubility, plasma stability (no acid-labile alerts), and a protease-cleavable
self-immolative trigger. The agent's objective transferred across cysteine, click, and
redox conjugation without human re-specification.
