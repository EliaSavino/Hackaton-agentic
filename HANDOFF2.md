# HANDOFF 2 — Autonomous ADC Linker Design (for the colleague)

State as of 2026-07-02. This hands off a **working payload-aware agentic pipeline** plus a
**reviewer critique** (`CRITIQUE.md`) and a **next-generation plan** (`PLAN_STUDY3.md`). Read
those two alongside this. The goal for the paper: a *meaty* 5-page manuscript in which the
**agents run the whole medicinal-chemistry workflow** — reading literature, constructing the
objective, designing synthesizable payload-matched linkers, and producing an actionable
shortlist — with a human only supervising/planning.

## 1. TL;DR — where we are

- **Study 1** (`deliverables/`): first autonomous ADC-linker campaign, 5-page paper. Done.
- **Study 2 revised** (`deliverables/study2/`): **payload-aware** design — one agent designs
  correctly for cytotoxins, oligonucleotides (ARC) and immunomodulators (ISAC). 5-page main +
  4-page supplementary, compiles clean. **This is the current best artifact.**
- **Reviewer critique** (`CRITIQUE.md`): the work reads as an excellent proof-of-concept but
  not yet a convincing *autonomous scientist*. Six weaknesses + a concrete "what next".
- **Next**: `PLAN_STUDY3.md` turns that critique into a supervised multi-agent workflow.

## 2. What already works (the assets you inherit)

| Capability | Where | How to run |
|---|---|---|
| Payload-aware scorer | `tools/payload_profiles.py`, `tools/adc_linker_objective.py` | `profile_for_payload(payload, trigger_meta)` |
| Literature-analysis step | `payload_profiles.derive_payload_rules()` | LLM-derived **with an API key**, else literature-encoded |
| Controlled grid (3-D) | `demos/adc_grid.py`, `demos/adc_study2.py` | `run_study2_grid(resume_dir='runs/grid_war3')` |
| REINVENT LinkInvent | `tools/reinvent_tools.py` | runs on the RunPod box over SSH (CPU) |
| Boltz-2 co-folding | `tools/boltz_tools.py`, `demos/adc_study.py` | pod GPU via `ssh_remote`; `finalize_study(...)` |
| Commercial benchmark + yardsticks | `tools/linker_benchmark.py` | QED/physchem/Morgan-novelty + calibration |
| Analysis + figures | `tools/adc_analysis.py` | grid stats + 6 figures |
| Paper writer | `tools/adc_study_paper.py` | 5pp main + supp LaTeX → PDF |
| RAG literature store | `data/rag.sqlite` + `rag-ingest` CLI | already holds the review set |
| The LangGraph agent loop | `src/hackathon_agents/agents/` (planner/critic/writer) | `cli design-adc-linkers` |

**Reproduce Study 2 revised end-to-end:**
```bash
ssh pod 'pkill -9 -f reinvent || true'
python -c "from hackathon_agents.demos.adc_study2 import run_study2_grid; run_study2_grid(resume_dir='runs/grid_war3')"
python -c "from hackathon_agents.demos.adc_study import finalize_study; finalize_study('runs/grid_war3/grid.json')"
```

## 3. The reviewer critique → where the plan answers it

| # | Critique weakness | Plan phase (`PLAN_STUDY3.md`) |
|---|---|---|
| 1 | "Agentic" claim under-proven (rules were literature-*encoded*, not LLM-extracted); expose the reasoning chain | **Phase A** — run the literature agent for real (keys on); emit retrieved chunks → extracted rules → reasoning → compiled scorer params → objective as auditable artifacts |
| 2 | Scoring is hand-designed; conclusions follow from construction | **Phase E** — a *non-encoded prediction* test: derive rules from a train split, predict behaviour the objective never encoded, check vs ground truth |
| 3 | Synthetic accessibility = biggest weakness | **Phase B** — retrosynthesis/route feasibility, building-block availability, step-count, medchem filters |
| 4 | Stability surrogate too simplistic (only flags hydrazones) | **Phase B** — mechanism-resolved stability (peptide / disulfide / maleimide / hydrolysis / plasma vs lysosomal) |
| 5 | Boltz = recognition, not cleavage | **Phase D** — reframe as substrate recognition / structural plausibility; optional scissile-geometry check |
| 6 | Payloads are abstract classes | **Phase C** — optimise around real payloads (MMAE, a siRNA/ASO stub, R848/imidazoquinoline) with real properties + DAR + site |
| next | Richer literature KB; actionable shortlist of 5/class with dossiers | **Phase A** (KB) + **Phase F** (5 per class: SMILES, rationale, closest analogue, synthesis, failure modes, validation) |

## 4. Environment & infrastructure (hard-won — don't relearn it)

- **Agent env python:** `/Users/es/miniforge3/envs/hackathon-agents/bin/python` (paramiko, rdkit,
  docx, pypdf). Always `PYTHONPATH=src`.
- **RunPod box (shared H200):** SSH config in `.env` (`REINVENT_SSH_HOST=103.196.86.112`,
  `PORT=11883`, key `~/.ssh/id_pods`). REINVENT runs **CPU** (pod torch cu130 vs driver → GPU
  unusable for REINVENT). Boltz uses a **separate** `/workspace/boltz_venv` (torch cu124) → GPU
  works, needs `--no_kernels`.
- **Shared-pod discipline (critical):** cleavable-scoring jobs are CPU-heavy → use
  `max_workers=5, steps=40, batch=32, timeout=1800`; **always `pkill -9 -f reinvent`** orphans
  before/after a killed run; launch long jobs **detached** (`( nohup … & )`) because harness
  background jobs get killed; the grid is **resumable** (`resume_dir=`).
- **API keys:** the LLM agent path (and the whole "autonomous reasoning" story) needs
  `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` set. The Study-2 run had none → rules were
  literature-encoded. **Phase A requires keys.** Model routing in `configs/agents.yaml`.
- **LaTeX:** `pdflatex` at `/Library/TeX/texbin`. Papers compile locally.

## 5. The new literature (staged in `data/`, ready to ingest)

Full-text PDFs backing the payload rules — the ARC/ISAC ones are the primary sources we
previously only had abstracts for:

| PDF | Paper | Payload class it grounds |
|---|---|---|
| `siRNA.pdf` | Antibody–siRNA conjugates without cationic assistance (Bioconj. Chem. 2025) | Oligonucleotide (ARC) — rigid non-cleavable |
| `ISAC.pdf` | TLR7 agonist–antibody conjugates through Fc effector function | Immunomodulator (ISAC) |
| `Immuno.pdf` | Imidazo[4,5-c]quinoline immune-stimulating ADCs | Immunomodulator (ISAC) |
| `biomedicines-11-03080.pdf` | Lysosomal-cleavable peptide linkers in ADCs | Cytotoxin (protease) |
| `ChemSocRev.pdf` | Stimulus-cleavable chemistry in controlled drug delivery (61 pp) | All (cleavage mechanisms) |
| `pharmacology.pdf` | Linker design impacts ADC PK/efficacy (Front. Pharmacol.) | Cytotoxin / stability |
| `songli2021.pdf` | ADC recent advances in linker chemistry | Cytotoxin / conjugation |

**Ingestion status: DONE.** All three payload PDFs were ingested into `data/rag.sqlite`
(now **8 documents / 183 chunks**; siRNA +16, ISAC +23, Immuno +19). Retrieval verified — e.g.
querying *"antibody siRNA conjugate rigid non-cleavable sulfo-SMCC"* returns the ARC paper's
"structurally stable ARCs" passage; *"TLR7 agonist ISAC linker cleavability"* returns the ISAC
paper. The corpus is **Phase-A-ready**: the extraction/rule-derivation agents can retrieve
directly. (Re-ingest any file with `rag-ingest <path> --db-path data/rag.sqlite`.)

## 6. Known limitations / honesty guards (keep these — they are why reviewers trust us)

- **Physicochemistry dominates**: the compact non-cleavable cap wins on drug-likeness under
  *every* payload rule, so we do **not** claim "cleavable wins for cytotoxins." The honest,
  demonstrable result is the payload-dependent *re-scoring* of cleavable linkers (Val-Cit
  0.70→0.45 under the oligo rule).
- **Boltz ipTM does not discriminate** (everything docks); we pivoted to **predicted affinity**
  (designed protease linkers 6–76 nM, non-cleavable control 787 nM). Affinity ≠ cleavage — frame
  as substrate recognition.
- **Rules were encoded, not LLM-derived** this run (no keys). Phase A fixes this.
- 3 pre-existing unrelated test failures (config model-pin ×2, CLI help-wrap flake) — not ours.

## 7. Immediate next actions (ordered, for you + the agents)

1. Set API keys; ingest `siRNA/ISAC/Immuno.pdf` into `data/rag.sqlite`.
2. Run **Phase A** (literature agent) with keys → capture the full reasoning chain as artifacts.
3. Stand up **Phase B** retrosynthesis + mechanism-stability scorers (the biggest credibility win).
4. Run **Phase E** non-encoded prediction (the headline rebuttal to the reviewer).
5. **Phase F** shortlist (5/class + dossiers) → the paper's actionable payload.

## 8. Architecture / repo map (confirmed)

**The agent loop — `src/hackathon_agents/graph.py` (`DiscoveryGraph`).** Five nodes, LangGraph
with a deterministic fallback runner:
`planner → chemist → tool_execution → critic → (loop back to chemist | writer)`.
State is `DiscoveryStatePayload` (`state.py`), max **3** passes. `_route_after_critic()` decides
loop-vs-writer. Every agent LLM call goes through `call_agent_model()` (`llm/model_helpers.py`)
and is **non-fatal** — deterministic logic completes the run if the LLM is off/unavailable.

| Node | File | Does | Key hooks |
|---|---|---|---|
| planner | `agents/planner.py` | plan + seed objective | detects ADC intent, seeds `metadata["reinvent"]`, `adc_goal_profile` |
| chemist | `agents/chemist.py` | generate candidates | opt-in `generate_with_reinvent()` / `generate_with_saturn()` via `metadata` |
| tool_execution | `graph.py:238–394` | run tools | RDKit, **`run_boltz_2()`**, ORCA/xTB, BayBE — all config-gated per RunMode |
| critic | `agents/critic.py` | score + steer | `score_adc_linker()`; autonomy via `goal_profile_overrides`, `reinvent_strategy_overrides` |
| writer | `agents/writer.py` + `graph._writer_node` | reports | `write_adc_paper()`, `write_latex_report()`, `write_artifact_index()` |

**LLM routing:** `ModelRouter.select_for_agent()` (`llm/router.py`), `LLMClient.complete()`
(`llm/client.py`), config in `configs/agents.yaml`. Providers: ollama, vLLM, OpenRouter,
Anthropic, OpenAI. Gate: env `HACKATHON_AGENT_LLM_MODE` = `off` | `auto` (default) | `always`,
plus a provider key. **For the autonomous-reasoning story, set `=always` + a key.**

**RAG:** `tools/rag_tools.py` — `ingest_rag_documents()`, `search_rag()`, `build_rag_context()`;
store `rag/store.py:RAGStore`; SQLite BM25-style lexical retrieval at `data/rag.sqlite`.
**Important: RAG is CLI-only right now (`rag-ingest`, `rag-search`) — it is NOT called from any
graph node.** Wiring retrieval into the agents is Phase A's core plumbing task (see PLAN_STUDY3).

**CLI (`cli.py`):** `demo`, `design-adc-linkers`, `design-adc-campaign`, `rag-ingest`,
`rag-search`, `prompt-terminal`, `mechanism-loop`. The ADC study/grid work runs through the
`demos/adc_*` scripts, not the CLI graph, today.

**Design patterns to exploit:** graceful LLM fallback; opt-in tool hooks via `state.metadata`;
config-gated tools per RunMode; critic mid-run steering; bounded 3-pass loop; artifact-index
provenance. The next-gen agents (extractor, rule-derivation, retrosynthesis/stability scorers,
validation, selector) slot onto these nodes — mapping table in `PLAN_STUDY3.md §1`.
