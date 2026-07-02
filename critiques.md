# Reviewer 2 — Critique of the ADC Linker Program (Studies 1–4) and the Study 4 Plan

Scope: I read `data/problemprompt.txt`, the full plan/handoff evolution (`PLAN.md`,
`PLAN_STUDY2.md`, `PLAN_STUDY3.md`, `PLAN_STUDY4.md`, `HANDOFF{,2,3,4}.md`), the two prior
external reviews (`CRITIQUE.md`, `CRITIQUE_S3.md`), the shipped Study 3 deliverables, **and the
source code that actually produced them**. Unlike the earlier reviews, this one is written with
code access, so it is about *what the pipeline really does* versus *what the manuscript claims*.

**Bottom line:** the narrative arc (payload-aware → autonomous scientist → visualize/tune) is
excellent and the right direction. But Study 3 as shipped presents **mock and hard-coded values
as scientific results**, and the Study 4 plan builds new features on top of that unvalidated
foundation without fixing it. Before the buddy runs Study 4, the integrity issues in Part I must
be closed, or every downstream claim inherits the defect. Study 4's own scope (Part II) also does
not address a single one of the nine points the external reviewer raised in `CRITIQUE_S3.md`.

---

## Part I — Integrity blockers (verified in code; fix before any Study 4 claim)

These are not stylistic. Each is a place where the manuscript/deliverable asserts a result that
the code does not actually compute. The team's own HANDOFFs repeatedly stress "honesty guards" —
these violate them.

### I.1 The Boltz "structural proof" in Study 3 is fabricated data
- `deliverables/study3/boltz.json` reports `Kd = 45 nM` (designed cleavable) and `Kd = 999 nM`
  (non-cleavable), `iptm` 0.85/0.25. These are **exactly** the hard-coded mock constants in the
  `except` branch of `demos/adc_study3.py:308-311` (`45.0 if p_class != "oligonucleotide" else
  999.0`). They are what the code emits **when Boltz fails / is not installed**, not measured
  predictions.
- The shipped non-cleavable SMILES `O=C1C=CC(=O)N1c1ccc(CO)cc1` is one of the **hard-coded mock
  linkers** from `adc_study3.py:153-157`, not a designed molecule.
- The `boltz.json` labels (`Maleimide/Val-Cit-PABC`) don't even match the labels the Study 3
  panel produces (`cytotoxin_cand_0`, `adc_study3.py:265`) — so the deliverable's Boltz block was
  not produced by the Study 3 code path at all; it was carried over/reassembled.
- The manuscript (`README.md`, `study3_manuscript.tex`) presents `Kd ≥ 999 nM` as "solid
  biophysical validation" and "complete non-substrate rejection." **This is presenting a mock
  fallback constant as an experimental result.** Highest-severity issue.

**Required fix:** the Boltz panel must run for real (pod GPU, `/workspace/boltz_venv`,
`--no_kernels`, as documented in `HANDOFF.md`), assert `status == "completed"` (not `"mock"`),
and the paper builder must **refuse to emit** any affinity claim whose source record has
`status == "mock"` or `ok == False`. If GPU is unavailable, the number cannot appear as a result
— label it explicitly "illustrative / not run."

### I.2 The Phase E "non-encoded prediction" — the headline claim — is not a test
The whole rebuttal to external-reviewer point #2 ("conclusions follow from construction") rests on
Phase E. In `adc_study3.py:232-254`:
- **E3 is literally `e3_pass = True`** (line 240) with the comment "verified via ... SMARTS
  matching." Nothing is computed. The manuscript reports "recovers clinical safety sequence
  zero-shot." It is a hard-coded `True`.
- **E1 does not withhold anything.** It calls `derive_literature_rules("oligonucleotide", ...)`
  against the *full* `rag.sqlite` (no leave-one-out split anywhere), then checks whether the
  returned string equals `"non-cleavable-rigid"` (line 237). There is no train/test separation,
  so it cannot test generalisation.
- Worse: when the LLM output fails to parse, `lit_reasoning.py:167-175` **hard-codes** the
  oligonucleotide rule to `cleavage_preference = "non-cleavable-rigid"`. So E1 can "pass" by
  comparing a constant to itself. The prediction and the ground truth are the same hard-coded
  string.

**Required fix:** E1 must (a) build a *reduced* RAG store with `siRNA.pdf` genuinely removed,
(b) run derivation against only that store, (c) persist the retrieved chunks + raw LLM completion
as artifacts, (d) compare to the withheld conclusion. E3 must actually score real clinical linker
SMILES through `score_mechanism_resolved_stability` and assert the ordering programmatically. If
either can't be done for real, the claim is deleted, not stubbed.

### I.3 Phase A "derived rules" never reach the optimiser (they're decorative)
`adc_study3.py:103` fetches `rules = derived_rule_cards[p_class]["rules"]` — and then never uses
it. The REINVENT objective is built from `warhead_pair` only (`build_adc_linkinvent_objective`,
lines 106-125, which is also **duplicated verbatim** — a copy-paste bug). The "autonomous
literature reasoning → compiled objective" pipeline that is the paper's entire thesis is **not
wired**: the agent's rules do not change what REINVENT optimises. This is the exact defect the
external reviewer flagged in `CRITIQUE.md#1` and `CRITIQUE_S3.md#1`, still unfixed and now masked
by a manuscript that claims it is fixed.

**Required fix:** the derived rule must parameterise the objective (cleavage preference → the
`CustomAlerts`/subscore inversion that already exists in `adc_linker_objective.py`; rigidity →
rotatable-bond window; stability priority → weight). Otherwise drop the "compiled objective"
claim. Also delete the duplicated objective block.

### I.4 "Real payloads" (Phase C) do not influence any score
`real_payloads.assemble_construct` joins linker and payload with a `.` (`real_payloads.py:49`) —
that is a **disconnected mixture** in SMILES, not a covalent conjugate. And the assembled
descriptors are never used: the ranking score is
`overall = 0.4*synth + 0.4*stab + 0.2` (`adc_study3.py:171`) — payload hydrophobicity/charge/size
enter **nowhere**. So "optimise around real payloads" (rebuttal to `CRITIQUE.md#6`) is not
happening; the payload is cosmetic. Also `siRNA` is a ~12-atom nucleotide stub, not an
oligonucleotide.

**Required fix:** either (a) form a real covalent bond at the attachment point and feed
conjugate-level logD/aromatic load into the objective, or (b) remove the "payload-aware
optimisation" claim and describe it honestly as post-hoc annotation.

### I.5 "Retrosynthesis" is a descriptor formula, not retrosynthesis
`PLAN_STUDY3.md §3` specified AiZynthFinder (real USPTO routes) as the *highest-priority* fix and
the "biggest credibility win." What shipped (`predictive_scorers.estimate_retrosynthetic_steps`)
is `base_steps = 2 + n_amides + 1.5*n_disulfides + ... + (MW-300)/100`, clamped to 2–12. There is
no route search, no building-block lookup, no reaction. The manuscript's "closed the
synthesizability gap, reduced from 11 steps to 4–7 steps" is a statement about an arbitrary
weighted count, not a synthesis.

**Required fix:** integrate AiZynthFinder (pip-installable, as the plan already scoped) for the
shortlist, OR rename the metric honestly ("heuristic complexity index") and stop reporting "linear
synthetic steps" / "routes."

### I.6 Silent mock substitution throughout
Multiple layers silently replace real output with fixed constants: mock SMILES
(`adc_study3.py:153-157`), mock Boltz (I.1), mock rules (I.2), `LLM_MODE=auto` (not `always`, per
`.env`) which — per your own `HANDOFF2 §6` — falls back to deterministic logic without failing.
The net effect is a pipeline that **cannot tell the operator when it stopped doing real science.**
No run artifact records `status: mock` in a way the paper builder checks.

**Required fix (single highest-leverage process change):** a provenance gate. Every number that
reaches LaTeX carries a `source ∈ {measured, llm, heuristic, mock}` tag; the paper builder
asserts no `mock` tag survives into a *results* claim and prints a provenance table in the
supplementary. Run with `HACKATHON_AGENT_LLM_MODE=always` for any run whose paper claims LLM
derivation, and persist the raw completions.

---

## Part II — Critique of the Study 4 plan itself

`PLAN_STUDY4.md` proposes three things: (A) 2D structure drawings, (B) agent-driven dynamic weight
tuning, (C) hierarchical cheap→targeted funnel. Assessed individually:

### II.1 It answers none of the external reviewer's open Study 3 asks
`CRITIQUE_S3.md` listed 9 gaps: real held-out prediction (#2/#3), a shortlist a chemist would
actually pick vs top-scoring (#4), autonomous control flow (#5), **uncertainty** (#6),
**failure-recovery narrative** (#7), richer experimental prioritisation (#8), biological realism
(#9). Study 4 addresses essentially none of these — it pivots to visualisation and self-tuning.
That's a strategic miss: the reviewer told you what would move the needle, and the plan spends its
budget elsewhere. At minimum, fold in #6 (uncertainty) and #7 (a genuine "critic caught a wrong
rule, agent revised" trace) — both are cheap and directly rebut the standing critique.

### II.2 Phase B "dynamic weight tuning" is dangerous without a frozen yardstick
Letting the Objective-Compiler agent freely tune `SCORE_WEIGHTS` (`PLAN_STUDY4.md §3`) **amplifies**
the exact circularity the external reviewer flagged (`CRITIQUE.md#2`): if the agent both sets the
weights and reports the winner, "our designs score well" becomes unfalsifiable. Self-tuning is only
defensible if success is measured on a **frozen, independent** metric the agent cannot touch (QED,
Morgan novelty, a held-out prediction, or real retrosynthesis from I.5). The plan must specify that
locked yardstick, and must log every weight change as an artifact with the agent's stated
rationale.

### II.3 Phase C funnel is the strongest idea — but its filter is currently meaningless
The cheap-exploration → targeted-RL funnel (`§4`) is genuinely good: cheap, scalable, on-brief
("cost-effective discovery"), low-risk. **But** Step 1 filters the raw pool by "RDKit med-chem
alerts, retrosynthetic step-counters, and solubility proxies" — and the step-counter is the fake
heuristic from I.5. A funnel that selects chemotypes by a meaningless feasibility score
concentrates the search on artifacts of the heuristic. Fix I.5 first, then the funnel is worth
building.

### II.4 Phase A drawings — good, but "scissile bond in red" must be detected, not asserted
2D depictions with handle/scissile/spacer highlighting (`§2`) are the cleanest, highest-value,
lowest-risk deliverable in the plan — a chemist reads structures, not SMILES. Requirement: the
handle, scissile bond, and solubiliser must be **identified programmatically** (SMARTS on the
assembled construct), verified against a few known linkers (Val-Cit-PABC, SMCC), and the drawing
must fail loudly if it can't locate a scissile bond — otherwise the highlight is decoration.

### II.5 The plan repeats the "top-scoring vs chemist-would-pick" gap
`CRITIQUE_S3.md#4` explicitly asked for the shortlist to be the molecules a medicinal chemist would
choose, with dossiers (analogue, route, failure modes, validation). Study 4 still draws "the top
1–3 candidates" by composite score (`§2`, `§5`). Same critique will recur. The shortlist selector
should apply a med-chem gate (real feasibility + alerts + novelty), not just `argmax(score)`.

---

## Part III — The improved plan the buddy should run (prioritised)

Do these in order. P0 is mandatory before writing any Study 4 paper.

**P0 — Restore integrity (turns the existing pipeline honest):**
1. Provenance gate (I.6): tag every value `measured|llm|heuristic|mock`; paper builder asserts no
   `mock` reaches a results claim; emit a provenance table in the supplementary. Run with
   `HACKATHON_AGENT_LLM_MODE=always`; persist raw LLM completions and retrieved RAG chunks.
2. Real Boltz or no Boltz claim (I.1): run on the pod GPU, assert `status=="completed"`; delete the
   45/999 mock constants from the results path.
3. Real Phase E (I.2): genuine leave-one-out RAG store minus `siRNA.pdf`; compute E3 from real
   clinical SMILES; delete `e3_pass = True` and the tautological E1.
4. Wire Phase A rules into the objective (I.3) and delete the duplicated objective block.
5. Feed payload into scoring or drop the payload-aware claim (I.4).
6. Real retrosynthesis (AiZynthFinder) or honest renaming (I.5).

**P1 — Study 4 features, made honest:**
7. Phase C funnel (II.3) — build it, but only after step 6 (so the filter means something).
8. Phase A drawings (II.4) — SMARTS-driven highlighting, verified on known linkers, fail-loud.
9. Phase B dynamic tuning (II.2) — allow it **only** against a frozen independent yardstick; log
   every weight decision + rationale as an artifact.

**P2 — Close the external reviewer's standing gaps (cheap, high-credibility):**
10. Uncertainty (`CRITIQUE_S3.md#6`): report confidence on each derived rule / recommendation
    (e.g. agreement across N verifier agents, retrieval support count).
11. One real failure-recovery trace (`#7`): show the critic catching a wrong rule and the agent
    revising — this is the single most convincing evidence of autonomy, and the graph already
    supports critic-driven re-seeding.
12. Chemist-grade shortlist (`#4`): med-chem-gated selection + dossiers, not `argmax(score)`.

---

## Definition of done (what makes the Study 4 paper defensible)

- No number in the paper traces to a `mock`/hard-coded constant; a provenance table proves it.
- The autonomous chain is real end-to-end for at least one payload class: retrieved chunks → raw
  LLM rule → **objective actually changed by that rule** → designs → validated on a metric the
  objective never optimised.
- At least one *genuine* held-out prediction (real leave-one-out, artifacts captured).
- Structures are drawn with programmatically-detected highlights, verified on known linkers.
- Every honesty guard the HANDOFFs already articulate is enforced *in code*, not just in prose.

The program is genuinely close to a compelling "autonomous medicinal-chemistry scientist" story.
The gap is no longer ambition — it's that the last mile was stubbed and then written up as done.
Close Part I and Study 4 becomes the paper the arc has been promising.

---

# Part IV — Review of the shipped `deliverables/study4/` (post-run)

Reviewed after the buddy ran Study 4. I checked the artifacts against the code and the raw
outputs, the same way as Part I. **Verdict: the Part I integrity blockers are genuinely fixed.**
This is a real, defensible iteration — a large qualitative jump from Study 3. There are still
substantive gaps, but they are honest-science gaps, not fabrications.

## What is now real (credit where due — verified, not taken on trust)
- **Boltz is real.** `boltz_jobs/*/output/.../predictions/` contain actual `*.pdb` structures,
  `pae/pde/plddt` tensors, and `affinity_*.json`; the reported Kd (43/44/74/1199 nM) derives from
  the real `affinity_pred_value` (e.g. immuno −1.364 → 43.2 nM). No more 45/999 mock constants.
  ipTM/plDDT vary per job. This fully closes Part I.1.
- **The held-out prediction is a real test.** `heldout_predictions.json` carries the full chain
  (retrieved passages → grounded exemplars → rule → objective → confidence), `leaked_sources: []`,
  and — the honest highlight — the oligonucleotide class, when its only ARC paper is withheld,
  returns **zero exemplars** and confidence **0.007** rather than inventing evidence. They even
  report a **miss** (`immunomodulator stability_match: False`). That is what a real, non-cherry-
  picked experiment looks like. Closes Part I.2.
- **Rules now compile into the objective.** `reasoning_chains.json` shows each derived rule
  producing a `canonical_spec` → `weights` block (cleavage regime, `max_rot_bonds`, per-term
  weights). Exemplars are `grounded: true` with source-quoted evidence from the real PDFs.
  Closes Part I.3 at the *derivation* level.
- **The LLM is genuinely on.** The `claude-opus-4.6` → `claude-opus-4-6` model-ID fix (README)
  was the real root cause of the silent fallbacks across Studies 2–3 — a good catch that
  retroactively explains I.6.
- **Drawings are real.** `draw_linker_constructs.py` classifies atoms by SMARTS
  (handle/scissile/spacer) with a documented priority order — programmatic, not asserted.

## Remaining weaknesses (ranked — these are what a reviewer will still hit)

### IV.1 The derived objective still does not *generate* the shortlist (loop not closed)
`shortlist.json` has `grid_path: deliverables/study3/grid_results.json` — which is itself the
**Study 2 grid** (its schema is `handles/triggers/payloads`, the old fixed-objective sweep). So
the 15 "actionable designs" are **selected from a cached pre-Study-4 pool**, then re-ranked; the
freshly compiled Phase-A objective is used to *filter*, not to *drive REINVENT generation*. The
central promise ("designs derived from the agent's reasoning") is therefore still one hop short:
derive-objective → **select from old pool**, not derive-objective → generate. `PLAN_STUDY4 §3`
(agent dynamically tunes weights → RL) is not actually exercised in what shipped.

**Consequence, visible in the data:** the cytotoxin rule derived "protease-cleavable / Val-Cit,"
but the **#1 delivered cytotoxin candidate is a pyridyl-disulfide**
(`Nc1c(C(=O)SSc2ccccn2)nnn1...`, handle "Disulfide", trigger labelled "Non-cleavable", flagged
`disulfide_reduction`). It's selected because the coarse "reward-cleavable" regime counts a
disulfide as cleavable — but it does **not** honour the class-specific derived motif (Val-Cit /
cathepsin B). The shortlist matches the regime, not the rule. Fix: run REINVENT with the compiled
per-class objective (even a short 40-step pass) so the delivered molecules are actually produced
by the derived rule, and enforce the specific motif in selection.

### IV.2 "Whole-conjugate" Boltz is still a disconnected mixture, not a conjugate
`boltz_whole_conjugate.json` and the dossiers still assemble as `linker_smiles`.`payload_smiles`
(a `.` — two separate species). Boltz co-folds the linker **and** the payload as **two
independent ligands** in the cathepsin-B pocket, not one covalent construct. The framing
("whole-conjugate co-fold") overstates it; the honest statement is "linker + payload co-present."
Part I.4 is not closed. Either bond them at the attachment point or rename the claim.

### IV.3 Retrosynthesis is still the descriptor heuristic (Part I.5 unaddressed)
Dossiers report `step_count: 6`, "Standard coupling steps" — still
`estimate_retrosynthetic_steps` (the `2 + n_amides + …` formula), no AiZynthFinder. The dossier
"proposed synthesis" is therefore LLM-narrated plausibility, not a validated route. Keep the
number but label it "heuristic complexity index," or wire AiZynthFinder for the 15 shortlisted
molecules only (cheap at n=15).

### IV.4 Confidence has a partly-fixed component
`self_confidence` is exactly **0.55** for both cytotoxin and immunomodulator (0.05 for oligo).
Check whether that is an LLM output or a default that kicks in when the model omits the field — if
the latter, the composite confidence is partly hard-coded and should be labelled as such in the
supplementary provenance.

### IV.5 The oligo showcase is a prior, not a derivation (frame carefully)
With zero exemplars, the still-correct "non-cleavable" oligo prediction comes from the LLM's
**parametric prior** (oligos are big/charged/stable), not from independent-paper reasoning. The
README frames this correctly as an *uncertainty-calibration* win (confidence collapses to ~0) —
keep it there. Do **not** let the paper drift into calling it a literature-derived recovery; it
is the opposite (evidence removed → it abstains). The `PLAN_STUDY4 §12` fix (add 2–3 more ARC
papers) is the right move to turn it into a genuine confident recovery.

### IV.6 Still no provenance gate in code (Part I.6 process fix outstanding)
The values are real *this* time, but nothing in the paper builder *enforces* it — there is no
`source ∈ {measured,llm,heuristic,mock}` tag that blocks a mock/default from reaching a results
claim. That gate is what makes the honesty durable across future runs; recommend adding it before
the next iteration, plus a provenance table in the supplementary.

## Definition of done for the Study 4 paper (updated)
- **Must:** regenerate the shortlist by running REINVENT under each class's *compiled* objective
  (close IV.1), so delivered molecules are produced by the derived rule and honour its specific
  motif; re-draw/re-Boltz those.
- **Should:** covalently assemble the conjugate for Boltz, or restate the claim (IV.2); label the
  retrosynthesis metric honestly or wire AiZynth for n=15 (IV.3); confirm `self_confidence`
  provenance (IV.4).
- **Framing:** keep the oligo case as calibration, not recovery (IV.5); add the provenance
  gate (IV.6).

Net: Study 4 is the first iteration I would let out of the building. The fabrications are gone and
the reasoning is genuinely visible and validated. The one gap that still separates it from its own
thesis is IV.1 — the derived objective must *make* the molecules, not just *pick* them.

---

# Part V — Review of the shipped `deliverables/study5/` (post-run)

Reviewed against artifacts, code, and raw run outputs, same as before. Study 5 responded to my
Part IV (which the team vendored as `CRITIQUE_S4.md`). **Verdict: Part IV is genuinely closed on
every point, and the loop is now shut end-to-end.** The fabrication era is over; this is the first
iteration whose central scientific claim is not only real but *interesting*. The remaining items
are frontier-of-method, not integrity.

## Verified real (checked, not trusted)
- **IV.1 closed — the objective now GENERATES the molecules.** `reinvent_runs/` holds real
  REINVENT artifacts (`rl_output_1.csv`, `reinvent.log`, `reinvent_inputs.smi`,
  `reinvent_config.json`) in per-class dirs named for the *derived* motif
  (`cytotoxin__Maleimide__Val-Cit-PABC`, `oligonucleotide__DBCO__Non-cleavable-rigid`,
  `immunomodulator__Maleimide__Val-Ala-PABC`). `generated_designs.json` has `mock: False`,
  `ok: True`, and the derived trigger is baked into `warhead_pair`, so every assembled design
  carries the motif by construction (the Boltz cytotoxin linker shows citrulline + PABC). The
  cytotoxin candidate is now a real Val-Cit design, not Study 4's stray disulfide.
  `shortlist.json` now sources from `designs_path` / `generated: True` — **no `grid_path`**. The
  derive→compile→generate→select→validate chain is closed.
- **IV.6 closed — provenance gate exists in code.** `tools/provenance.py` defines
  `MockValueError`, `boltz_source()`, and `assert_no_mock_in_results`, called before results emit.
  The honesty guard is now enforced in code, per my P0.1.
- **Boltz real and discriminating.** `boltz.json`: Kd 8.9 nM (Val-Cit cytotoxin design) vs 35 nM
  (clinical control) vs 108.7 nM (rigid non-cleavable ARC), varied ipTM/plDDT — consistent with
  the study-4 code path I verified against raw affinity tensors.
- **IV.5 closed — and it produced the program's best result.** Corpus genuinely grew **8 → 31
  documents / 666 chunks** (verified in `data/rag.sqlite`). The ARC leave-one-out withholds the
  siRNA showcase paper (`leaked_sources: []`) and derives **protease-cleavable Val-Cit at 0.81
  from 9 grounded exemplars**, each quoting real retrieved text (e.g. "DYNE-101 (DTX-C-008), which
  features a Val-Cit linker" — present verbatim in retrieved chunk 9 of `s41434-026-00621-5`).
  This is a genuine, non-encoded, literature-grounded derivation that *disagrees* with the
  withheld paper's rigid-non-cleavable conclusion. Faithful to its sources, and honestly surfaced
  as "the field is contested." That is exactly the "conclusions are literature-derived, not
  encoded" proof the whole arc was chasing.
- **IV.2 / IV.3 / IV.4 resolved honestly.** Whole-conjugate reframed as "linker + payload
  co-present" (two ligands); step-count demoted to a reported complexity index with continuous
  Ertl SA_Score as the axis; `self_confidence` confirmed varied LLM output.

## Remaining weaknesses (frontier, ranked)

### V.1 The confidence metric conflates evidence *volume* with evidence *consensus* (the real one)
This is the subtle flaw hiding inside the headline. In the ARC held-out, the 9 grounded exemplars
**genuinely disagree with each other**: DYNE-101 / DYNE-251 = Val-Cit (cleavable); AOC-1001 =
non-cleavable SMCC; others = disulfide, or non-cleavable maleimide (MALAT1 ASO). The evidence is
~50/50 cleavable vs non-cleavable — yet the agent collapses to a *single* rule
(`protease-cleavable`) at **0.81 confidence**, because the confidence function rewards
`n_grounded` (9) and not the internal agreement of those exemplars. The scientifically correct
output is "clinical AOC linker choice is **split / target-dependent**" — which the README prose
says, but the machine's rule and its 0.81 confidence do not. A field that is genuinely contested
should drive confidence **down**, not up. **Fix (and the natural Study 6 headline): make
confidence disagreement-aware** — compute exemplar consensus (fraction agreeing with the modal
rule) and fold it into the score, and let the rule itself carry a `contested: true` + a minority
report when exemplars split. That turns "contested" from a caption into a *computed, calibrated*
output — the most compelling next step the program has available.

### V.2 The `whole_conjugate: true` flag still labels a disconnected mixture
The prose was fixed (IV.2), but `boltz.json` still carries `whole_conjugate: true` on records whose
assembled species is a `linker.payload` two-fragment mixture. The data field now contradicts the
honest prose. Rename the flag (`co_present: true`) or actually bond the fragments — otherwise a
future reader of the JSON re-inherits the overclaim.

### V.3 "Synthesizability" is a standard heuristic, not a route (acceptable, but state it)
SA_Score (Ertl fragment-contribution) is a legitimate, peer-accepted metric and demoting the fake
step-counter is the right call — but SA_Score is still **not** a retrosynthetic route. The paper
may say "synthetic accessibility (Ertl SA)"; it must not say "synthesis route" or "N steps" as a
result. Real routes (AiZynthFinder on the 15 shortlisted) remain the honest upgrade and are cheap
at n=15.

### V.4 The generative sample is shallow
`n_generated: 25` per class (best_score ~0.66). Real generation is now happening — but 25 molecules
→ a 5-shortlist is a thin funnel; seed variance and chemotype coverage are essentially untested.
Scale to a few hundred per class (more RL steps / larger batch) so the shortlist is a selection,
not nearly the whole pool. Scope/scale limitation, not integrity.

### V.5 Study 5 doesn't ship the raw Boltz outputs
Unlike Study 4 (`boltz_jobs/` with PDBs + affinity tensors), Study 5 ships only `boltz.json`. The
values are consistent with the verified-real code path, but shipping the raw `affinity_*.json`
(or referencing their location) would let a reviewer re-derive the Kd. Reproducibility nit.

### V.6 Standing biological realism still simplified (external `CRITIQUE_S3.md#9`)
DAR, conjugation site, Fc effects, payload-specific PK remain out of scope. Fine to defer, but the
paper should name it as the boundary rather than imply conjugate-level realism.

## Bottom line
Study 5 is publishable-grade on the honesty axis: every Part IV gap is closed in code, the
generate-from-derived-objective loop is shut, and the ARC contested-linker finding is a real,
grounded, non-obvious scientific result that a lookup-table system could not have produced. The
one flaw worth chasing next is V.1 — the confidence number should fall when the literature
disagrees. Fix that and the "autonomous scientist that knows what it doesn't know" thesis is
demonstrated, not just asserted.

---

# Part VI — Minor revision: writing & figures only (no new data)

Scope per request: purely stylistic — how the Study 5 manuscript *reads* and which figures *drive
the point*. No experiment re-runs; every fix below is rewording, restructuring, relabelling, or
re-plotting the JSON already in `deliverables/study5/`. The science is sound (Part V); this is
about making a strong result legible.

## The one-line diagnosis
The paper hides its best result behind process. The genuinely exciting finding — **the agent
discovers that ARC linker cleavability is a contested question** — is buried in Results §4.2,
while the abstract, title, and methods lead with meta-machinery (auditable chains, provenance
gates, "closing the loop of the prior iteration"). A first-time reader wades through *how honest
the pipeline is* before learning *what it found*. Fix the ordering and the emphasis and the paper
reads in half the time.

## A. Title & abstract (highest-impact, 20 minutes)
1. **Title is three lines with a full-sentence subtitle.** Cut to one line. e.g. *"An Autonomous
   Agent that Derives ADC Linker Rules from the Literature, Designs the Molecules, and Flags When
   the Field Disagrees."* Drop the "the Derived Rule Reads… " clause.
2. **The abstract is a single ~250-word sentence-pile** (stacked em-dashes and semicolons). Break
   into 5 plain sentences: (i) the linker requirement inverts with payload; (ii) we read 31 papers
   and derive per-class rules with a grounded LLM; (iii) **the rules generate the molecules**
   (REINVENT); (iv) the held-out test discriminates robust rules from a contested one — the ARC
   rule flips to cleavable Val-Cit from the clinical AOC literature; (v) one sentence on provenance.
   Lead (iv) earlier — it is the hook.
3. **Retire the self-reference.** "closing the central gap of the prior iteration," "not selected
   from a cached pool," "the prior iteration left open" assume the reader read Study 4. In a
   standalone paper this is noise — compress to a single Discussion sentence.

## B. Tone: stop saying "honest" (15 minutes)
"honest/honestly" appears ~6× in the main text (abstract, methods, two results, table captions,
discussion), plus a methods subsection literally titled *"Honest scorers and a provenance gate."*
Repeatedly asserting honesty reads *defensively* — as if arguing with a reviewer (you are, but the
published version shouldn't). Say it once, then **show** it via the SI provenance table. Rename
§2.2 to "Scorers and provenance"; delete the standalone honesty adjectives elsewhere.

## C. Figure strategy — what actually drives the point

**Reorder: the held-out bar chart should be Figure 1.** `fig_heldout.png` *is* the thesis made
visual — robust (green, recovers) vs contested (red, flips). It's clean, correct, and on-message.
Right now it's Figure 2, behind the weakest figure. Promote it.

### Fig_heldout (the strong one — promote, minor polish)
- The green "cleavable 0.96 ROBUST" label collides with the title/legend band — nudge down or
  shrink the two-line title.
- **Wording/figure mismatch to fix (ties to Part V.1):** the bars show the contested ARC case
  barely moving (0.87→0.81) while the *robust* cytotoxin *jumps* (0.78→0.96). So "contested" is
  shown by the **rule flipping direction + the red bar**, not by a confidence drop. The caption
  says this correctly; but the abstract/§4.2 phrase "its confidence tracks the evidence" is **not**
  what the bars show (confidence hardly falls when contested). Reword the text to "the derived
  *direction* flips," or the figure and prose will read as contradicting each other.

### Fig_reasoning_cascade (currently Fig 1 — the weakest; has a rendering BUG)
- **Rendering bug:** in the first box of each row the bold coloured heading ("Retrieved
  literature") is drawn **on top of** the passage text — it's illegible (see the cytotoxin box).
  Fix the layout so the heading sits above the body.
- **It dumps raw filename slugs** ("identification-of-a-novel-linker-enabling-the-bioconjugation-
  of-a-cyclic-dinucleotide…", "s0960894x23002263-main"). Replace with human citations (Author
  Year) or a single representative title. Slugs look like a leaked internal path.
- **It shows counts, not evidence.** Four boxes of "12 passages / 15/15 grounded / rule / weights"
  is metadata. The most convincing thing this figure could do — for free, from the JSON — is show
  **one real retrieved quote → the exemplar it grounds → the derived rule**, for one class. e.g.
  the ARC row: the literal "DYNE-101 (DTX-C-008)… Val-Cit linker" passage → the exemplar → the
  flipped rule. That single concrete chain proves grounding better than "15/15."
- It only shows the *full-corpus* ARC rule (non-cleavable) so it doesn't foreshadow the contested
  headline. If it stays Fig 1, let the ARC row hint at the tension.

### Structure_gallery (good, on-brief — tighten)
- **Terminology mismatch:** the per-molecule sublabels say **"steps=12"** while the table/text
  now (correctly) call it a **"complexity index."** Align to "cplx idx" everywhere — otherwise
  you reintroduce the "N synthetic steps" overclaim the paper explicitly retired.
- **Three near-duplicate molecules per class** (cytotoxin 0.657/0.626/0.626 are the same scaffold).
  It makes the designs look non-diverse. Show **one clean exemplar per class**, larger, and push
  the rest to the SI — or pick three genuinely distinct chemotypes if the pool has them.
- **The red "scissile" highlight is diffuse** — it paints several carbonyls, not *the* Cit–PABC
  scissile amide. Tighten the SMARTS so red marks the single scissile bond; right now the legend
  overpromises what the colour means. (Re-plot only, no new data.)

## D. Tables
- **Table 2 (15 dossiers) looks padded.** Within each class every row is identical except the
  SMILES and the Tc: cytotoxins all Cplx=12/Stab=0.85/P(succ)=0.14; immuno all the same; oligo
  nearly so. Fifteen rows that vary in one column advertise low diversity. Either collapse to a
  per-class summary + one representative SMILES, or add a column that genuinely varies (SA_Score
  value, the specific spacer) so the table earns its length.
- **P(succ) will trip readers:** oligo designs (0.65–0.85) outrank the clinically-standard Val-Cit
  cytotoxins (0.14). That inversion is an artefact of the complexity index penalising peptides
  (which the text half-admits). Either add one clause explaining it *at the table*, or drop the
  P(succ) column from the main text and keep it in the SI.
- **Table 1:** the withheld-paper cell reads "siRNA, exploring-the-poten" (truncated slug). Use a
  readable short citation.

## E. Reconcile the two confidence numbers (avoids a real reader stumble)
Fig 1 (cascade) shows full-corpus confidence (cyto 0.78, ARC 0.87, ISAC 0.82); Table 1 / Fig 2
show held-out confidence (0.96, 0.83, 0.81). A reader who sees "0.78" in Fig 1 and "0.96" in
Table 1 for the *same* cytotoxin rule will think one is wrong. Label them explicitly everywhere:
"full-corpus confidence" vs "held-out confidence."

## F. Line-level nits
- Drop hedges: "more interesting than a clean recovery, we think" → cut "we think."
- Em-dash density is very high throughout; convert half to commas/periods for breathing room.
- **Submission blocker (not stylistic, but flag it):** the author list includes "Claude" and
  "J.A.R.V.I.S" as equal-contribution authors. Many journals (ICMJE, Nature, ACS) prohibit AI
  tools as authors — move to an Acknowledgements / "AI tools used" statement or the paper bounces
  at desk.

## Priority order (all doable without re-running anything)
1. Split the abstract into 5 sentences and lead with the contested-ARC result; trim the title. (A)
2. Promote fig_heldout to Figure 1; fix the label collision. (C)
3. Fix the cascade figure's text-overlap bug and swap slugs → citations (or replace box 1 with a
   real quote→exemplar→rule chain). (C)
4. Align "steps" → "complexity index" in the gallery; de-duplicate to one molecule/class. (C, D)
5. Reword "confidence tracks evidence" → "the direction flips"; label full-corpus vs held-out. (C, E)
6. Cut the "honest" repetition; move the AI authors to Acknowledgements. (B, F)

None of these touch the data. They move the paper from "a dense, defensive methods report" to
"a short paper with one sharp, well-illustrated finding" — which is what the result deserves.

---

# Part VII — Proposed figure plan (new figures, buildable from the shipped JSON)

All of these draw only on files already in `deliverables/study5/` (`reasoning_chains.json`,
`heldout_predictions.json`, `generated_designs.json` [per-molecule `subscores` + per-class
`weights`], `boltz.json`, `dossiers.json`) — **no re-runs**. I verified the fields exist.

**The narrative spine (what actually happened), 5 beats:**
1. an agent reads 31 papers → derives payload-class rules, grounded + confidence-scored;
2. those rules *compile into objectives that generate the molecules* (loop closed);
3. a held-out test discriminates robust rules from a contested one (ARC flips) — **because the
   evidence is genuinely split**;
4. the generated molecules are recognised by cathepsin B (co-fold);
5. the output is an actionable, provenance-tagged shortlist.

For a 5-page single-column paper: **4 figures + 2 compact tables** is the sweet spot (5 figures
only if some run half-width). Below, ranked; the single best driver is Figure 2.

---

### ★ Figure 2 (the money figure) — Held-out discrimination *and its cause*
**New composition panel + revised bars. The one figure that proves the finding.**
Two panels sharing the class x-axis:
```
 conf │ cyto      ISAC      ARC
 1.0  │ ▓▓ ██     ▓ ▓       ▓  ▒        ██ full-corpus   ▓ held-out(robust)  ▒ held-out(contested)
      │ 0.78→0.96 0.82→0.83 0.87→0.81
      │ cleavable cleavable NONcleav→CLEAVABLE (flip)
 ─────┼─────────────────────────────────
 evid │ [██████████]  [████████░░] [█████▒▒▒▒▒]   ← grounded exemplars:
 comp │  cleavable     cleavable    ~50/50 split      ██ favour cleavable ▒ favour non-cleavable
```
The **bottom "evidence-composition" strip is new and decisive**: for each class, a horizontal
stacked bar = fraction of grounded exemplars favouring cleavable vs non-cleavable. Cytotoxin/ISAC
are near-uniform → robust; **ARC is ~50/50 → contested**. This *shows* "contested" instead of
asserting it, and it fixes the Part V.1 problem head-on: the confidence barely moves (0.87→0.81),
so the bars alone don't explain the flip — the composition strip does. Directly from
`heldout_predictions.json` exemplar `linker` labels (ARC: Val-Cit, Val-Arg, Val-Cit vs
non-cleavable SMCC, disulfide, non-cleavable maleimide — already classifiable).

---

### ★ Figure 1 — Hero: one molecule's journey from paper to pose
**Replaces the broken cascade. Concrete, end-to-end, single worked example (use the cytotoxin).**
```
 REAL QUOTE                 GROUNDED          DERIVED RULE          GENERATED            CO-FOLD
 "VCit-PABC has good    →   exemplar:     →   cleave=protease   →   [drawn structure  →  in cathepsin B
  stability in human        MMAE /            rigid=semi            of the actual        Kd = 8.9 nM
  serum" [Biomed 2023]      Val-Cit-PABC      stab=high             designed linker]     (recognition)
                            (grounded✓)       conf 0.78 + weights   carries Val-Cit
```
Five stages, one molecule threaded through all of them. The current Figure 1 (cascade) stops at
"weights" and shows *counts*; this version shows the *actual quote → actual structure → actual
Kd*, i.e. the whole thesis in one horizontal strip. Data: `reasoning_chains` (passage+exemplar+
rule+weights) → `generated_designs` (the SMILES → RDKit draw) → `boltz.json` (Kd). Kills the
text-overlap bug and the filename-slug problem by construction.

---

### Figure 3 — The rules steer the chemistry (loop closed, quantitatively)
**New. The proof that the derived objective *shaped* the molecules, not just labelled them.**
```
  weight heatmap (class × term)        75 generated designs in property space
  ┌───────────────────────────┐        flex │        ○ oligo (rigid cap, flexible spacer)
  │        sol flx clv stab   │        1.0  │      ○○○
  │ cyto   1.0 .5  1.0 .85    │             │   ●●        ● cyto  ▲ ISAC  ○ oligo
  │ ISAC   1.0 .2  1.0 .70    │        0.3  │  ▲▲ ●●●     ✦ = clinical refs
  │ oligo  1.0 .9  0.8 .85    │             └───────────────────── cleavability →
  └───────────────────────────┘                  0            1
```
Left: the three objective weight-vectors differ (oligo flexibility 0.9 vs cytotoxin 0.5;
cleavability 0.8 vs 1.0). Right: a scatter of all 75 generated molecules (x = cleavability
subscore, y = flexibility subscore, colour = class) showing the three classes land in **different
regions because their objectives differ**, with clinical linkers overlaid. This is the strongest
rebuttal to "the rule is decorative" — the output distribution is visibly rule-shaped. Data:
`generated_designs` `weights` + per-molecule `subscores` (both present).

---

### Figure 4 — Structural recognition (co-fold), honestly framed
**Revised from raw `boltz.json`.** A single log-scale Kd dot plot:
```
 Kd(nM) 1 ── 10 ── 100 ── 1000
        ●cyto(8.9)  ✦clinical(35)   ○ARC-rigid(109)   ▲ISAC(46)
        └ tighter = better cathepsin-B recognition (NOT cleavage) ─┘
```
Val-Cit design ≈ clinical substrate ≪ rigid ARC. Optional inset: one rendered co-fold pose
(cytotoxin design seated in the pocket) if a PDB is on disk — visceral, but the dot plot alone
carries it. Caption states affinity ≠ cleavage.

---

### Figure 5 (optional / swap with Fig 4 for a chemistry audience) — Fixed structure gallery
**Revised.** One clean designed structure **per class** (not three near-duplicates), large,
handle/scissile/spacer highlighted with the *tightened* scissile SMARTS, each annotated with the
derived motif it carries + SA_Score + nearest clinical analogue (Tc). This is the "a chemist can
act on this" panel. Data: `shortlist`/`dossiers` + `draw_linker_constructs`.

---

## Recommended sets
- **Keep-4 (best all-round):** Fig 1 (journey) · **Fig 2 (held-out + composition)** · Fig 3
  (rules steer chemistry) · Fig 4 (co-fold Kd). Plus Table 1 (held-out) and a **3-row** dossier
  table (one representative/class; full 15 → SI).
- **Keep-3 (if space is tight):** Fig 1 · Fig 2 · Fig 5. Drops the quantitative proof (Fig 3) and
  the co-fold but keeps journey → finding → actionable structures — the cleanest chemistry story.
- **Audience swap:** modelling/ML venue → keep Fig 4 (Boltz); med-chem venue → keep Fig 5
  (structures). Fig 3 is the best "fourth" and the one most worth adding if you have the half-page.

## The single best driver
If you cut to one figure: **Figure 2 with the evidence-composition strip.** It is simultaneously
the result (robust vs contested), the mechanism (why ARC flips — the split evidence), and the
uncertainty story (the agent's rule follows the literature's actual balance). Everything else in
the paper exists to earn that panel; make it the centrepiece and build the abstract around it.

---

# Part VIII — Study 6 final polish + scoring-rubric alignment

Study 6 executed Parts V.1/VI/VII faithfully: V.1 fixed (disagreement-aware confidence, ARC now
0.50→0.33 FLIPS), the abstract/title/tone cleaned, and the 4-figure spine built exactly as
proposed. Figures render cleanly — the journey overlap-bug is gone and Fig 2 (held-out + evidence
composition) is the self-justifying centerpiece. What's left is genuinely polish.

## The one reader-stumble to fix (credibility, not cosmetics)
**Cytotoxin confidence goes UP when a paper is withheld: 0.60 (full corpus) → 0.97 (held-out)**
(Table 1 and Fig 2). Removing evidence *raising* confidence looks like a bug to a careful reader.
It isn't — the full-corpus retrieval pulls in noisier/less-consistent exemplars that the
disagreement-aware metric penalises, while the held-out subset is cleaner — but the paper never
says so. **Add one clause** ("full-corpus confidence is lower where retrieval mixes in
off-topic exemplars; the held-out subset is more consistent"), or lead with the held-out number
and demote the full-corpus one. Otherwise the robust cases undercut the very metric the ARC story
depends on.

## Figure polish (all no-data, caption/label/scale only)
- **Fig 4 (co-fold) is the weak one — mostly white space for 4 points.** Two cheap fixes: (i)
  humanise the internal job labels (`cyto-Maleim-0` → "Val-Cit cytotoxin design", `olig-DBCO-0` →
  "rigid ARC design", mark the star "clinical substrate" inline); (ii) either shrink to half-width
  beside Fig 3, or add the rendered cathepsin-B **pose inset** (the Study-4 `boltz_jobs/*.pdb`
  already exist — rendering an existing structure is not a re-run). The pose is what makes
  "recognition" visceral; the bare dot plot underuses a full figure slot.
- **Fig 1:** the citation reads `[biomedicines-11-0308]` (truncated, and inconsistent with the
  "Balamkundu 2023" used elsewhere) — unify to the human citation. De-code the `cleave=…/->`
  shorthand to "protease-cleavable, semi-rigid → objective."
- **Fig 2 (top panel):** y-axis runs to 1.4 but the tallest bar is 0.97 — cap at ~1.1 so bars
  fill the panel instead of floating.
- **Fig 3 caption** slightly oversells: the y-axis (cleavable vs non-cleavable) is fixed by the
  welded trigger, so the real separation is the rotatable-bond axis. Say "separate by class,
  driven mainly by the rigidity knob" rather than implying two independent emergent axes.

## Scoring-rubric alignment (novelty · in-silico feasibility · paper quality)
The rubric weights (1) hypothesis novelty, (2) in-silico feasibility, (3) paper completeness.

- **(2) In-silico feasibility — strong, leave it.** Real REINVENT generation from the compiled
  objective, a discriminating Boltz co-fold, a genuine leave-one-paper-out, and calibrated
  confidence. This is the paper's best axis and it's well-shown.
- **(3) Paper quality — now strong.** Clean 4-figure spine, provenance-tagged, honest limitations,
  5 pp + SI. Do the polish above and it's done.
- **(1) Novelty — the weakest axis, and the one worth investing the remaining hours in.** The
  paper's *finding* (ARC linker cleavability is contested; clinical AOCs trend to cleavable
  Val-Cit against the early rigid-non-cleavable siRNA rule) is genuinely non-obvious — but it's
  framed as *surfacing a tension*, not as *a hypothesis*. The rubric rewards a **clear, falsifiable
  hypothesis**. Convert the observation into one: e.g. *"For antibody–oligonucleotide conjugates,
  a protease-cleavable Val-Cit linker will match or outperform the rigid non-cleavable sulfo-SMCC
  standard on [tumour payload release / potency], because the clinical AOC literature has already
  moved that way — and our agent derived it independently."* Then point to the in-silico evidence
  you already have (the Val-Cit ARC design co-folds/recognises where the rigid one doesn't) as the
  feasibility proof-point *for that hypothesis*. Same data, but now the paper *states a prediction
  the field can test*, which is exactly what criterion (1) scores. The meta-contribution
  (an agent whose confidence tracks literature consensus) is a strong secondary novelty — keep it,
  but lead the abstract's hook with the concrete ARC prediction, not the machinery.

## Bottom line
The honesty and figures are done. The single highest-leverage remaining move is **framing** for
criterion (1): promote the contested-ARC observation into an explicit, falsifiable hypothesis and
make it the paper's headline claim. Then fix the 0.60→0.97 explanation and the Fig 4 white space,
and it's submission-ready.

---

# Part IX — Figure 3 corrections + an ISAC stability error (found in review)

Three figure-honesty fixes for `fig3_rules_steer.png` and one **substantive scientific error** in
the shipped weights, surfaced while answering nitpicks on Fig 3.

## IX.1 The "flexibility" heatmap column is mislabelled (and the two panels contradict)
The left column labelled **flexibility** is a *scoring weight*, and the term it weights actually
**rewards rigidity**: `adc_linker_objective.py:162` applies a `reverse_sigmoid` on rotatable bonds
(`low=2, high=max_rot_bonds`), which scores *fewer* rotatable bonds near 1.0. So a **higher
"flexibility" weight → the objective pushes *harder* to rigidity → fewer rotatable bonds.** That is
why oligonucleotide (weight 0.90) has the *fewest* rotatable bonds — not a contradiction, a naming
trap. Worse, the two panels label the same axis with opposite words: left = "flexibility", right =
"rotatable bonds (rigidity knob)". **Fix:** rename the column `rigidity (low-rot-bond reward)`, and
add the per-class `max_rot_bonds` setpoint (5 / 10 / 14) — that setpoint, not the weight, is the
real driver of the scatter separation and is currently invisible.

## IX.2 The Fig 3 scatter y-axis is decorative (jitter, not signal)
The right-panel vertical spread is cosmetic jitter: `adc_study6_figures.py:121` plots
`y = (1 if cleavable else 0) + hash-based ±0.11`. The true y is binary and **fixed by construction**
(the welded trigger determines cleavable vs not), so height encodes nothing. **Fix:** either add
"(points jittered for visibility)" to the caption, or — better — put a *real* quantity on y
(stability or SA subscore) so the panel is a genuine 2-D separation instead of a 1-D one dressed up.
This also retires the caption's "two rule knobs" overstatement (only the x-axis does work).

## IX.3 The weights are a developer rubric keyed by the agent's category (tag them heuristic)
Every number in the weight heatmap comes from a **hardcoded lookup**, not agent-tuned or
literature-measured values: `profile_for_payload` (`payload_profiles.py:137-148`) maps the agent's
*categorical* rule to fixed weights (`rigidity=="rigid"→0.9`; `stability_priority=="paramount"→1.0`,
`=="high"→0.85`; untouched terms keep the `ADCGoalProfile` defaults, which is why cytotoxin's 0.50
is just the default). The agent chooses the *bucket* (grounded in exemplars); a human chose what the
bucket is worth. This is the correct, non-circular design (see Part II.2) — but the paper must label
these weights **`heuristic` (a deterministic rule-compilation)**, not imply the agent optimised
continuous values, and the two-decimal precision ("0.85") overstates what is really ~3 buckets.

## IX.4 SUBSTANTIVE: the ISAC stability weight is wrong — it should be the highest, not the lowest
Verified in the shipped run (`reasoning_chains.json`):

| Class | stability_priority (derived) | stability weight |
|---|---|---|
| Cytotoxin | high | 0.85 |
| Oligonucleotide (ARC) | high | 0.85 |
| **Immunomodulator (ISAC)** | **standard** | **0.70 (lowest)** |

This is backwards on the biology. An ISAC carries a **TLR7/8 agonist**; premature or off-target
systemic release drives **cytokine-release syndrome / severe systemic immune-inflammatory (allergic)
reactions**, so plasma stability and correct biodistribution are the *safety-critical* axis — the
place a payload "going where it shouldn't" is most dangerous. ISAC stability should be **paramount
(≈1.0), the highest of the three classes.** The team's own encoded prior already says this —
`payload_profiles.py:78` sets ISAC `stability_priority="paramount"`, with the comment
"immunomodulators must not release systemically" — but the **LLM-derived rule regressed it to
'standard'** (0.70) and the pipeline shipped the weaker value. Root cause: the ISAC evidence is thin
(1 grounded exemplar, `n_sources=1`), so the LLM defaulted the stability sub-decision — and unlike
the cleavage rule, that sub-decision is **not** confidence-gated.

**Fix (pick one, all cheap):**
- Floor it in the compiler: immunomodulator stability weight `>= 0.9` (a domain safety guard), or
- give the rule-derivation LLM the ISAC systemic-toxicity prior as a few-shot / instruction so it
  derives "paramount", and
- gate low-evidence sub-decisions: when a class's grounded exemplars are sparse, fall back to the
  encoded domain prior rather than the model default.

This also strengthens the paper: it's a concrete case where the agent's *confidence* machinery
(Part V.1) should extend beyond the headline cleavage rule to the stability sub-rule — right now a
thinly-evidenced, safety-critical decision shipped at full apparent authority.

---

# Part X — Version 7 bake-in (independent-reviewer fixes, verified + consolidated)

The v6 update landed the big things: §2.2 now states the confidence formula explicitly, the
abstract leads with the falsifiable ARC prediction (the Part VIII rubric-for-novelty advice), Fig 4
adds a top-k stress-test, and the Boltz ~1-log-unit noise caveat reframes "10 nM ≈ 35 nM" as
*same-regime* rather than a match. An independent reviewer then found a residual derivability bug
plus two count slips. I verified all of them against the shipped JSON; here is the ordered v7 list.

## X.1 (highest value, ~10 min) ISAC confidence is not derivable from Table 1 — add `n`
The paper now says "every confidence is derivable," which invites arithmetic-checking — and ISAC
fails it. Formula: `C = E·P`, `E = min(1, n/6)`, `n` = **total** grounded exemplars. Verified in
`heldout_predictions.json`: ISAC has **n = 5** grounded exemplars, of which only **1 is
cleavage-labelled** (Val-Cit; the other 4 are "unspecified"). So `E = 5/6 = 0.83`, `κ = 1`,
`P = 1`, `C = 0.83` ✓. But **Table 1's "Evidence" column shows `1/0`** — that is `n_c/n_n`, the
cleavage-labelled split, *not* `n`. A juror who computes `E` from `1/0` gets `1/6 ≈ 0.17` and
concludes the number is wrong. **Fix:** add an **`n (grounded)`** column to Table 1 (ISAC = 5), or
a one-line footnote defining that "Evidence = n_c/n_n while C uses total n." Do this first — it
directly protects the claim you just added.

## X.2 (one honest sentence) State that ISAC's confidence rides on evidence volume, not consensus
Because ISAC has `n_c+n_n = 1`, `κ = 1` trivially and it **cannot be flagged contested by
construction** (the rule needs `n_c+n_n ≥ 3`). So its 0.83 is driven almost entirely by evidence
volume `E`, not demonstrated consensus. §3.3 half-admits this; make it explicit — otherwise a juror
frames it as the metric flattering a one-vote class. One sentence: *"ISAC's robustness reflects
evidence volume, not tested consensus: with a single cleavage-labelled exemplar it cannot be flagged
contested, so its confidence is a lower bound on uncertainty."*

**Note this compounds with Part IX.4:** ISAC is the *same* class whose stability weight shipped too
low (0.70, should be paramount ≈1.0). Both stem from thin ISAC evidence + un-gated sub-decisions —
v7 should fix the stability weight *and* caveat the confidence. Adding 1–2 ISAC papers to the corpus
would fix both at once (raises `n` past the contested threshold and grounds the stability rule).

## X.3 (2 min each) Two count mismatches — reconcile
- **Paper count:** the abstract/Methods say **"30 primary papers"** but the Conclusion still says
  **"31 papers"** (both strings are in `adc_linker_study6.tex`). The RAG store (`data/rag.sqlite`)
  actually holds **31 documents** — so confirm the true number (30 papers + 1 non-paper doc? or one
  dropped?) and use it consistently in all three places + the SI.
- **Design count:** the Discussion says "generation samples **25** designs per class" while §3.6 /
  Table 2 reference "all **fifteen**." Not contradictory (25 generated/class → 15 shortlisted, 5×3)
  but it reads as a mismatch. State it as "25 generated per class → 15 shortlisted (5/class)."

## X.4 Still open from earlier parts (fold into v7 if not already done)
- **Part IX.1–IX.3 (Fig 3):** rename the "flexibility" heatmap column → `rigidity`; expose
  `max_rot_bonds` (5/10/14); caption the scatter jitter (or put a real quantity on y); label the
  weights `heuristic` (developer rubric keyed by the agent's category).
- **Part IX.4 (ISAC stability = 0.70):** raise to paramount (≈1.0) — TLR7/8 systemic release →
  cytokine-release syndrome / severe systemic reactions; the encoded prior already says paramount.

## Order for v7
1. Add `n` to Table 1 (X.1) — protects the derivability claim.
2. ISAC honesty sentence (X.2) + ISAC stability fix (IX.4) — same class, do together.
3. Reconcile 30/31 and 25/15 (X.3).
4. Fig 3 relabelling (IX.1–IX.3).

None change the result. After X.1–X.3 the arithmetic is check-proof and the counts are consistent —
which is exactly what the "provenance-gated, nothing hidden" story needs to survive a careful juror.
