# PLAN — Study 3: The Autonomous Medicinal-Chemistry Scientist

Response to `CRITIQUE.md`. The thesis moves from *"an agent that designs payload-aware
linkers"* to *"an autonomous scientist that reads the literature, constructs its own
objective, designs **synthetically realistic**, payload-matched linkers, and returns an
**experimentally actionable** shortlist — with its full reasoning chain exposed."*

The paper is still **5 pages**, but *meaty*: the density comes from the agents doing the whole
workflow (dozens of literature extractions, multiple predictive scorers, a non-encoded
validation, per-candidate dossiers) while the human is **only supervisor/planner**. Everything
in the manuscript should be traceable to an agent artifact.

---

## 0. The one-paragraph pitch (what wins)

A supervised swarm of specialised agents reads seven primary papers, extracts dozens of
payload–linker exemplars, **derives** the payload-class design rules (not us), compiles them
into a scorer that now includes **retrosynthetic feasibility and mechanism-resolved stability**,
designs linkers around **real payloads** (MMAE, siRNA, R848), and returns **5 candidates per
class** each with a synthesis route and validation plan. We prove the agent is doing science —
not fitting our scorer — with a **held-out, non-encoded prediction** that matches ground truth.

---

## 1. Architecture: agents own the workflow, human supervises

A **supervisor** (the planner node / human-in-the-loop) sequences the phases below and reviews
each artifact; specialised agents do the work, many **fanned out in parallel** and checked by
an **adversarial critic**. This extends the existing LangGraph loop (`agents/planner.py`,
`agents/critic.py`, `graph._writer_node`) with new agent roles, and is orchestrated as a
deterministic multi-agent **workflow** (fan-out → verify → synthesize per phase).

```
SUPERVISOR (planner/human)
 ├─ Phase A  Librarian → Extractor×7 (parallel, 1/paper) → Rule-derivation → Objective-compiler
 ├─ Phase B  Scorer-builder → {Retrosynthesis, Stability-mechanism, Aggregation, Payload-aware} services
 ├─ Phase C  Payload-binder (attach real payloads: MMAE / siRNA / R848 + properties, DAR, site)
 ├─ Phase D  Design agent (REINVENT LinkInvent) → Structural agent (Boltz, recognition framing)
 ├─ Phase E  Validation agent (non-encoded prediction + adversarial verification)
 ├─ Phase F  Selector/critic → 5 candidates/class + dossiers
 └─ Phase G  Writer → 5-page paper + reasoning-trace supplementary
```

**Mapping onto the existing `DiscoveryGraph` (`graph.py`).** The current graph is 5 nodes —
`planner → chemist → tool_execution → critic → (loop | writer)`, max 3 passes, every LLM call
via `call_agent_model()` with a deterministic fallback, and critic autonomy through
`CriticReviewResponse.goal_profile_overrides` / `reinvent_strategy_overrides`. The new roles
slot in without rewiring the loop:

| New agent role | Slots into | Concrete change |
|---|---|---|
| Librarian + Extractor + Rule-derivation | **new `research` node before `planner`** (or a pre-graph Phase-A workflow) | reads RAG, emits the KB + rules into `state.metadata` |
| Objective-compiler | **`planner`** | `profile_for_payload` becomes the *rule-derivation output*, seeded into `metadata["adc_goal_profile"]` |
| Design agent | **`chemist`** (already calls `generate_with_reinvent`) | per real payload/context |
| Retrosynthesis / Stability-mechanism / Aggregation scorers | **`tool_execution`** (config-gated tools, like Boltz) | new `ToolResult`-returning tools |
| Structural agent | **`tool_execution`** (`run_boltz_2` already there) | recognition framing |
| Validation + Selector | **`critic`** (already scores + steers) | non-encoded prediction + shortlist |
| Writer | **`writer`** (`write_adc_paper`) | + reasoning-trace supplement |

**The critical gap to close:** RAG (`tools/rag_tools.py`: `ingest_rag_documents`, `search_rag`,
`build_rag_context`) is **not currently called from any graph node** — it is CLI-only
(`rag-ingest`, `rag-search`). Phase A's whole point is to **wire retrieval into the agents** so
the design rules are derived from retrieved evidence in-loop, with the chain captured in
`state.metadata` and the artifact index. This is the single highest-leverage plumbing change.

**Turning the LLM on:** the real reasoning path needs `HACKATHON_AGENT_LLM_MODE=always` (or
`auto`) **plus** a provider key (`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`, or a local Ollama/vLLM
endpoint); routing is in `configs/agents.yaml` via `ModelRouter.select_for_agent()`. Without it,
agents silently fall back to deterministic logic — which is exactly why Study 2's rules were
"literature-encoded."

**Orchestration note (for the planner/me):** run this as a `Workflow` — Phase A extractors
fan out one-per-PDF; Phase B scorers run as parallel services over each candidate; Phase E
spawns N independent adversarial verifiers per prediction and keeps it only on majority. The
supervisor reads each phase's synthesized artifact before launching the next.

---

## 2. Phase A — Autonomous literature reasoning (rebuts critique #1)

**Goal:** make the agent's reasoning the visible source of the scientific conclusions.

1. **Ingest** the 7 staged PDFs (`data/*.pdf`) into `data/rag.sqlite` via `rag-ingest`
   (siRNA/ISAC/Immuno are new; the reviews are partly there).
2. **Extractor agents (fan-out, 1 per paper)** mine a structured exemplar table — for each
   ADC/ARC/ISAC in the paper: `{payload, payload_class, linker, conjugation_chemistry,
   cleavage_mechanism, plasma_stability, release_trigger, biological_outcome, citation}`.
   Target **dozens of rows** across the corpus (the "richer KB" the reviewer asks for).
3. **Rule-derivation agent** reasons over the KB (real LLM, **API keys ON**) to produce each
   payload class's design rule, emitting the full chain as first-class artifacts:
   **retrieved chunks → extracted exemplars → intermediate reasoning → derived rule →
   compiled scorer parameters → final REINVENT objective.**
4. **Objective-compiler agent** turns the rule into scorer weights/toggles
   (`profile_for_payload` becomes the *output* of the agent, not a hand-written function).

**Deliverable:** a *Reasoning Appendix* (supplementary) showing the chain end-to-end, and a main-
text figure of the KB → rule → objective pipeline. Now the conclusions demonstrably originate
from the agent. **Requires API keys** (see HANDOFF2 §4).

---

## 3. Phase B — A scorer a chemist would trust (rebuts #3, #4)

Replace heuristic objectives with predictive components, each an independent scoring service the
Objective-compiler can weight:

- **Retrosynthetic feasibility (highest priority — the biggest weakness):** run retrosynthesis on
  every candidate (AiZynthFinder is the pragmatic choice — pip-installable, USPTO model; ASKCOS
  as a stretch). Emit route depth, **estimated step count**, building-block availability, and a
  route-success score. **Reject candidates with no ≤5-step route**; prefer 3–5 steps.
- **Mechanism-resolved stability:** replace the hydrazone-only alert with a model that scores
  distinct liabilities — **peptide cleavage, disulfide reduction, maleimide deconjugation,
  hydrolysis, plasma vs lysosomal stability** — from SMARTS + literature-derived rate ordering
  (from the Phase A KB), calibrated against known clinical rankings.
- **Aggregation / hydrophobicity:** conjugate-level HI/logD proxy, aromatic-ring load.
- **Medchem sanity filters:** PAINS/reactive-alerts, ring strain, valence sanity.

**Deliverable:** the new scorer, plus a Pareto showing designed linkers now **close the
synthesizability gap** with commercial linkers (the honest trade-off from Study 2 is the thing
we most want to fix).

---

## 4. Phase C — Real payloads, not abstract classes (rebuts #6)

Attach **representative payload molecules** to the warhead pair and carry their properties into
scoring:

- Cytotoxin → **MMAE** (and/or DXd); Oligonucleotide → a **siRNA/ASO stub** (polyanionic,
  high-MW); Immunomodulator → **resiquimod / imidazoquinoline (R848)**.
- Score the **assembled ADC fragment** (payload + linker + handle) so payload hydrophobicity,
  charge and sterics actually influence the optimum; annotate a target **DAR** and **conjugation
  site**. This makes the payload-dependent optimum a property of real chemistry, not a toggle.

---

## 5. Phase D — Structural proof, honestly framed (rebuts #5)

- Keep Boltz-2 co-folding but **frame it as substrate recognition / structural plausibility**,
  never as proof of cleavage. Lead with **predicted affinity** (which discriminates) and state
  ipTM does not.
- Stretch: check **scissile-bond geometry** relative to the catalytic dyad (Cys29/His199 of
  cathepsin B) in the top complexes — a stronger recognition argument than affinity alone.
- **Parallelise the co-fold panel (easy speedup).** Measured: a single ~260-residue co-fold
  uses only **~3.7 GB of the 143 GB H200** (peak GPU util ~96% in a short burst; ~89 s wall,
  most of it CPU-side prep). So **30+ co-folds fit in VRAM at once**, yet `demos/adc_study.py:
  run_boltz_panel` currently runs them **sequentially**. Fan them out (concurrent `run_boltz_2`
  jobs, or a batched Boltz invocation) to cut the structural-proof stage from ~15–30 min to a
  few minutes — and it frees budget to co-fold the full shortlist rather than a top-k subset.
  Note the CPU-side prep is the real per-job cost, so cap concurrency to keep the shared pod's
  cores from thrashing (mirror the REINVENT `max_workers` discipline).

---

## 6. Phase E — The non-encoded prediction (rebuts #2 — the headline)

The reviewer's sharpest point: because cleavability rules are encoded, the payload ranking isn't
independent evidence. We answer with predictions the objective **never encoded**:

- **(E1) Leave-one-paper-out rule derivation.** Withhold the siRNA (ARC) paper from Phase A;
  have the agent predict the ideal ARC linker from the *rest* of the literature; then reveal the
  held-out paper's conclusion (rigid non-cleavable sulfo-SMCC) and show the agent arrived there
  independently. Tests literature→rule generalisation, not the scorer.
- **(E2) Emergent structural agreement.** The objective never sees cathepsin B; yet designed
  cleavable linkers show tight predicted affinity and non-cleavable ones do not (already observed
  in Study 2: 6–76 nM vs 787 nM). Elevate this as an **emergent, non-encoded** corroboration.
- **(E3) Clinical-ranking recovery.** Have the *mechanism-stability* model (Phase B, not tuned to
  outcomes) reproduce the **known** plasma-stability ordering of real clinical linkers
  (hydrazone/Mylotarg worst; Val-Ala > Val-Cit; non-cleavable most stable) — a prediction against
  ground truth it was not fit to.

Each prediction is checked by **N independent adversarial verifier agents**; keep only those that
survive. This is the section that turns "proof-of-concept" into "autonomous scientist."

---

## 7. Phase F — Actionable shortlist + dossiers (rebuts "what next" #4)

Selector/critic agent narrows hundreds of candidates to **5 cytotoxin + 5 oligonucleotide + 5
ISAC** linkers. Each gets a one-row **dossier**: `SMILES · design rationale · closest literature
analogue (from the KB) · proposed synthesis (from retrosynthesis) · expected failure modes ·
suggested validation experiment`. This is the paper's payload — what a chemist actually acts on.

---

## 8. Phase G — The writer + supervisor

Writer agent produces the **5-page main** (thesis: autonomous scientist; headline: the
non-encoded prediction + the synthesizable shortlist) and a **reasoning-trace supplementary**
(the Phase A chain, the KB, the full 15-candidate dossiers, all scorer components). The
supervisor (planner/human) reviews each phase artifact and re-seeds where the critic flags gaps.

---

## 9. Scope for the hackathon (prioritised — do the top three if time is short)

The three that most directly rebut the reviewer and make the strongest 5 pages:

1. **Phase A** (real LLM literature reasoning + exposed chain) — rebuts #1, needs only API keys.
2. **Phase B retrosynthesis + mechanism-stability** — rebuts #3 and #4, the biggest credibility gains.
3. **Phase E non-encoded prediction** (E1 + E3) — rebuts #2, the headline experiment.

Phases C/D/F/G then package it. Phases C (real payloads) and the AiZynthFinder integration are the
main feasibility risks (install + compute); E2 is free (already in hand) and is the safe fallback
for the non-encoded-prediction claim.

## 10. Success criteria

- Every scientific conclusion in the paper is traceable to an **agent artifact**, not a hand-set
  parameter (Phase A chain shown).
- Designed linkers are **synthesizable** (≤5-step routes) — the synthesizability gap closes.
- At least one **non-encoded prediction** validates against held-out literature or clinical data.
- A **15-candidate actionable shortlist** with synthesis + validation plans.
- Still **5 pages**, with the depth carried by the agents and the supplementary reasoning trace.
