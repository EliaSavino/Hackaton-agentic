"""Study 4 — Grounded, uncertainty-aware literature reasoning + held-out prediction.

Study 3's ``tools/lit_reasoning.derive_literature_rules`` proved the retrieval →
extraction → derivation chain works, but (a) it silently falls back to *hardcoded*
rules when the LLM is unavailable, (b) it never records which passage each exemplar
came from, and (c) it emits no confidence. Those three gaps are exactly the reviewer's
CRITIQUE_S3 points #1 (expose the reasoning), #2/#3 (a genuine held-out prediction) and
#6 (uncertainty).

This module rebuilds the chain so it is:

* **Grounded** — every exemplar must cite a *retrieved* passage; ungrounded exemplars
  are flagged, not trusted.
* **Uncertainty-aware** — each derived rule carries a confidence built from grounding
  ratio, source diversity and internal agreement.
* **Honest under failure** — there is **no hardcoded rule fallback**. If the LLM call
  fails or returns unparseable output, the result is ``llm_ok=False`` and the rule is
  ``None`` (an *abstain*), so a leave-one-paper-out test can never "predict" a planted
  answer.
* **Held-out capable** — passages from withheld source documents are excluded at
  retrieval time, so the agent literally never sees the paper it is being tested against.

The output feeds the Study 4 "reasoning waterfall" figure and the leave-one-paper-out
table.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from hackathon_agents.rag import RAGStore, DEFAULT_RAG_DB_PATH
from hackathon_agents.llm.client import LLMClient, CompletionRequest
from hackathon_agents.config import AppConfig
from hackathon_agents.logging_config import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Retrieval queries per payload class (kept explicit so the paper can cite them)
# --------------------------------------------------------------------------- #
PAYLOAD_QUERIES: dict[str, str] = {
    "cytotoxin": (
        "cytotoxic payload ADC linker cleavable Val-Cit-PABC cathepsin B protease "
        "plasma stability lysosomal release maleimide"
    ),
    "oligonucleotide": (
        "antibody siRNA oligonucleotide conjugate ARC linker non-cleavable rigid "
        "sulfo-SMCC stability gene silencing"
    ),
    "immunomodulator": (
        "immune stimulating antibody conjugate ISAC TLR7 TLR8 agonist imidazoquinoline "
        "linker cleavable plasma stability cytokine"
    ),
}


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _extract_json(content: str) -> Any:
    """Best-effort JSON extraction from an LLM completion (handles code fences)."""
    text = (content or "").strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    try:
        return json.loads(text)
    except Exception:
        # Try to locate the first balanced {...} or [...] blob.
        for opener, closer in (("{", "}"), ("[", "]")):
            start = text.find(opener)
            end = text.rfind(closer)
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except Exception:
                    continue
        raise


def _norm_source(value: str | None) -> str:
    """Normalise a source label to the RAG document title stem for comparison."""
    if not value:
        return ""
    s = str(value).strip().lower()
    s = s.rsplit("/", 1)[-1]
    for ext in (".pdf", ".txt", ".md", ".docx"):
        if s.endswith(ext):
            s = s[: -len(ext)]
    return s.strip()


# --------------------------------------------------------------------------- #
# Step 1 — retrieval with provenance and optional source withholding
# --------------------------------------------------------------------------- #
def retrieve_passages(
    store: RAGStore,
    payload_class: str,
    *,
    limit: int = 10,
    exclude_titles: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return the top passages for a payload class, each with full provenance.

    ``exclude_titles`` names source documents to *withhold* (leave-one-paper-out):
    matching passages are dropped **before** the agent sees anything, so the held-out
    paper never enters the reasoning context. We over-fetch then filter so ``limit``
    stays effective after exclusion.
    """
    query = PAYLOAD_QUERIES.get(payload_class, f"linker design rules for {payload_class} conjugates")
    excluded = {_norm_source(t) for t in (exclude_titles or []) if t}
    raw = store.search(query, limit=limit * 4 if excluded else limit)
    passages: list[dict[str, Any]] = []
    for r in raw:
        title_stem = _norm_source(r.title) or _norm_source(r.source_path)
        if title_stem in excluded:
            continue
        passages.append(
            {
                "idx": len(passages) + 1,
                "source": title_stem,
                "title": r.title,
                "source_path": r.source_path,
                "chunk": r.chunk_index,
                "score": round(float(r.score), 3),
                "text": r.text.strip(),
            }
        )
        if len(passages) >= limit:
            break
    return passages


def _passages_block(passages: list[dict[str, Any]], max_chars: int = 11000) -> str:
    blocks, remaining = [], max_chars
    for p in passages:
        header = f"[{p['idx']}] SOURCE={p['source']} | chunk {p['chunk']} | score {p['score']}"
        block = f"{header}\n{p['text']}"
        if len(block) > remaining:
            block = block[: max(0, remaining - 3)].rstrip() + "..."
        if not block.strip():
            continue
        blocks.append(block)
        remaining -= len(block) + 2
        if remaining <= 0:
            break
    return "\n\n".join(blocks)


# --------------------------------------------------------------------------- #
# Step 2 — grounded exemplar extraction (no hardcoded fallback)
# --------------------------------------------------------------------------- #
def extract_exemplars(
    client: LLMClient,
    payload_class: str,
    passages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """Extract conjugate exemplars, each grounded in a numbered retrieved passage.

    Returns ``(exemplars, llm_ok)``. ``llm_ok`` is ``False`` if the LLM call failed or
    produced unparseable output — the caller must treat that as *abstain*, never as a
    silent default.
    """
    valid_sources = {p["source"] for p in passages}
    prompt = f"""You are a senior ADC literature-curation agent. Below are numbered passages
retrieved from a literature database for the '{payload_class}' payload class. Each passage is
labelled with its SOURCE document.

Extract every antibody-conjugate exemplar that is *actually described in these passages*.
Do NOT use outside knowledge. If a fact is not in the passages, do not invent it.

For each exemplar output:
- payload: the payload molecule/class named in the passage
- linker: the linker architecture (e.g. Val-Cit-PABC, sulfo-SMCC, non-cleavable)
- conjugation: the conjugation chemistry if stated (else "unspecified")
- cleavage: one of "protease-cleavable" | "acid-cleavable" | "disulfide-cleavable" | "non-cleavable"
- plasma_stability: "low" | "moderate" | "high" | "very high" if stated (else "unspecified")
- evidence: a short (<=25 word) verbatim-ish quote from the passage supporting this exemplar
- source: the exact SOURCE label of the passage it came from (must be one of: {sorted(valid_sources)})

Passages:
{_passages_block(passages)}

Output raw JSON only, exactly:
{{"exemplars": [{{"payload": "...", "linker": "...", "conjugation": "...", "cleavage": "...", "plasma_stability": "...", "evidence": "...", "source": "..."}}]}}"""

    resp = client.complete(
        CompletionRequest(
            model_alias="science_reasoning",
            messages=[
                {"role": "system", "content": "You are a precise ADC bio-curator. Ground every claim in the given passages. Output raw JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=2500,
        )
    )
    if not resp.ok:
        logger.warning("Exemplar extraction LLM call failed: %s", resp.error)
        return [], False
    try:
        parsed = _extract_json(resp.content)
    except Exception as exc:
        logger.warning("Exemplar JSON parse failed: %s", exc)
        return [], False

    exemplars = parsed.get("exemplars", []) if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
    # Ground each exemplar against the retrieved sources.
    for ex in exemplars:
        src = _norm_source(ex.get("source"))
        ex["source"] = src
        ex["grounded"] = src in valid_sources
    return exemplars, True


# --------------------------------------------------------------------------- #
# Step 3 — rule derivation (no hardcoded fallback)
# --------------------------------------------------------------------------- #
def derive_rule(
    client: LLMClient,
    payload_class: str,
    exemplars: list[dict[str, Any]],
    passages: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, bool]:
    """Derive the design rule from grounded exemplars. Returns ``(rule, llm_ok)``.

    ``rule`` is ``None`` if the LLM fails — an honest abstain, so a held-out test cannot
    surface a planted default.
    """
    grounded = [e for e in exemplars if e.get("grounded")]
    basis = grounded or exemplars
    prompt = f"""You are a molecular-design oracle. Using ONLY the exemplars below (extracted from
the literature for the '{payload_class}' payload class), derive the linker design rule. Reason
from the evidence; if the evidence is thin or conflicting, say so and lower your confidence.

Exemplars (each cites its source passage):
{json.dumps(basis, indent=2)}

Determine:
1. cleavage_preference: one of "protease-cleavable" | "non-cleavable-rigid" | "non-cleavable-flexible" | "acid-cleavable"
2. rigidity: "rigid" | "semi-rigid" | "flexible"
3. stability_priority: "standard" | "high" | "maximum"
4. conjugation_recommendation: list of handles
5. solubilizing_requirements: list
6. rationale: 2-3 sentences grounded in the exemplars
7. self_confidence: your own 0.0-1.0 confidence that this rule is correct given the evidence

Output raw JSON only with exactly those keys."""

    resp = client.complete(
        CompletionRequest(
            model_alias="frontier_reasoning",
            messages=[
                {"role": "system", "content": "You are an expert ADC chemist. Derive rules only from the given exemplars. Output raw JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1200,
        )
    )
    if not resp.ok:
        logger.warning("Rule derivation LLM call failed: %s", resp.error)
        return None, False
    try:
        rule = _extract_json(resp.content)
    except Exception as exc:
        logger.warning("Rule JSON parse failed: %s", exc)
        return None, False
    if not isinstance(rule, dict) or "cleavage_preference" not in rule:
        return None, False
    return rule, True


# --------------------------------------------------------------------------- #
# Step 4 — normalise + compile the LLM rule into scorer parameters
# --------------------------------------------------------------------------- #
def normalize_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Map the LLM's free-text rule onto the canonical scorer spec, recording the map.

    canonical cleavage_preference ∈ {reward, penalize, ignore}; rigidity ∈
    {moderate, rigid, flexible}; stability_priority ∈ {standard, high, paramount}.
    """
    cp = str(rule.get("cleavage_preference", "")).lower()
    if "non-cleavable" in cp or "noncleavable" in cp:
        canon_cleave = "penalize"
    elif "cleavable" in cp:
        canon_cleave = "reward"
    else:
        canon_cleave = "ignore"

    rg = str(rule.get("rigidity", "")).lower()
    canon_rigid = "rigid" if "rigid" in rg and "semi" not in rg else ("flexible" if "flex" in rg else "moderate")

    sp = str(rule.get("stability_priority", "")).lower()
    if sp in ("maximum", "paramount") or "max" in sp or "paramount" in sp:
        canon_stab = "paramount"
    elif sp == "high":
        canon_stab = "high"
    else:
        canon_stab = "standard"

    return {"cleavage_preference": canon_cleave, "rigidity": canon_rigid, "stability_priority": canon_stab}


# Minimum number of grounded exemplars that must *state a plasma-stability level*
# for the LLM's stability sub-decision to be trusted over the encoded domain prior.
STABILITY_EVIDENCE_MIN = 3
_STAB_WEIGHT = {"paramount": 1.0, "high": 0.85, "standard": 0.7}
_STAB_UNSPEC = {"", "unspecified", "unknown", "none", "n/a", "na", "not specified"}


def _stability_evidence_count(exemplars: list[dict[str, Any]] | None) -> int:
    """Grounded exemplars that state a definite plasma-stability level (not 'unspecified')."""
    return sum(
        1 for e in (exemplars or [])
        if e.get("grounded") and str(e.get("plasma_stability", "")).strip().lower() not in _STAB_UNSPEC
    )


def _domain_stability_floor(payload_class: str | None) -> float | None:
    """The encoded domain-prior stability weight for a class (the safety floor)."""
    if not payload_class:
        return None
    from hackathon_agents.tools.payload_profiles import PAYLOAD_CLASSES
    spec = PAYLOAD_CLASSES.get(payload_class)
    if not spec:
        return None
    return _STAB_WEIGHT.get(str(spec.get("stability_priority", "")).lower())


def compile_objective(
    rule: dict[str, Any],
    *,
    payload_class: str | None = None,
    exemplars: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compile the derived rule into concrete scorer weights + cleavage regime.

    Mirrors ``payload_profiles.profile_for_payload`` but is driven by the *LLM's* rule,
    so the optimisation objective is genuinely a function of the agent's reasoning.

    ``payload_class``/``exemplars`` enable a **low-evidence safety gate** (Reviewer IX.4):
    a safety-critical sub-decision (plasma stability) must not ship under-weighted just
    because the LLM downgraded it on thin evidence. When the class states fewer than
    ``STABILITY_EVIDENCE_MIN`` grounded plasma-stability exemplars, the stability weight
    is floored to the encoded domain prior (never lowered) rather than the model default.
    """
    canon = normalize_rule(rule)
    weights = {"solubility": 1.0, "size": 1.0, "flexibility": 0.5,
               "synthesizability": 1.0, "stability": 0.7, "cleavability": 1.0}
    pref = canon["cleavage_preference"]
    if pref == "ignore":
        weights["cleavability"] = 0.0
        require_cleavable = False
    elif pref == "penalize":
        weights["cleavability"] = 0.8  # rewards *absence* of a cleavable motif
        require_cleavable = False
    else:
        weights["cleavability"] = 1.0
        require_cleavable = True

    max_rot_bonds = 10
    if canon["rigidity"] == "rigid":
        max_rot_bonds = 5
        weights["flexibility"] = 0.9
    elif canon["rigidity"] == "flexible":
        max_rot_bonds = 14
        weights["flexibility"] = 0.2

    if canon["stability_priority"] == "paramount":
        weights["stability"] = 1.0
    elif canon["stability_priority"] == "high":
        weights["stability"] = 0.85

    # Low-evidence safety gate: thin plasma-stability evidence -> fall back to the
    # encoded domain prior (e.g. ISAC/immunomodulator is 'paramount' because premature
    # systemic TLR7/8 release drives cytokine-release syndrome).
    stab_evidence_n = _stability_evidence_count(exemplars)
    floor = _domain_stability_floor(payload_class)
    stability_gated = False
    if floor is not None and stab_evidence_n < STABILITY_EVIDENCE_MIN and floor > weights["stability"]:
        weights["stability"] = floor
        stability_gated = True

    return {
        "canonical_spec": canon,
        "cleavage_regime": pref,
        "require_cleavable_motif": require_cleavable,
        "max_rot_bonds": max_rot_bonds,
        "weights": weights,
        "stability_gated": stability_gated,
        "stability_evidence_n": stab_evidence_n,
    }


# --------------------------------------------------------------------------- #
# Step 5 — confidence
# --------------------------------------------------------------------------- #
def rule_confidence(
    rule: dict[str, Any] | None,
    exemplars: list[dict[str, Any]],
    passages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Confidence in the derived rule: grounding ratio × source diversity × agreement."""
    if rule is None:
        return {"score": 0.0, "label": "abstain", "n_exemplars": len(exemplars),
                "n_grounded": 0, "n_sources": 0, "agreement": 0.0, "self_confidence": 0.0}

    grounded = [e for e in exemplars if e.get("grounded")]
    n_ex = len(exemplars)
    n_gr = len(grounded)
    grounding_ratio = (n_gr / n_ex) if n_ex else 0.0
    sources = {e["source"] for e in grounded}
    n_sources = len(sources)

    # Internal agreement: fraction of grounded exemplars whose cleavage direction
    # matches the derived rule's direction (cleavable vs non-cleavable).
    canon = normalize_rule(rule)
    rule_noncleave = canon["cleavage_preference"] == "penalize"
    agree = 0
    for e in grounded:
        ex_noncleave = "non-cleavable" in str(e.get("cleavage", "")).lower()
        if ex_noncleave == rule_noncleave:
            agree += 1
    agreement = (agree / n_gr) if n_gr else 0.0

    self_conf = float(rule.get("self_confidence", 0.0) or 0.0)
    self_conf = min(max(self_conf, 0.0), 1.0)

    # Blend: grounding is the backbone; diversity and agreement modulate; the model's
    # own stated confidence gets a minority vote.
    score = (0.40 * grounding_ratio
             + 0.20 * min(n_sources / 3.0, 1.0)
             + 0.25 * agreement
             + 0.15 * self_conf)
    score = round(min(max(score, 0.0), 1.0), 3)
    label = "high" if score >= 0.7 else ("medium" if score >= 0.45 else "low")
    return {
        "score": score, "label": label,
        "n_exemplars": n_ex, "n_grounded": n_gr, "n_sources": n_sources,
        "sources": sorted(sources), "agreement": round(agreement, 3),
        "self_confidence": self_conf,
    }


# --------------------------------------------------------------------------- #
# Orchestrator — the full reasoning chain (one auditable artifact)
# --------------------------------------------------------------------------- #
def build_reasoning_chain(
    payload_class: str,
    config: AppConfig,
    *,
    db_path: Path | str = DEFAULT_RAG_DB_PATH,
    limit: int = 10,
    exclude_titles: list[str] | None = None,
) -> dict[str, Any]:
    """Run retrieval → grounded extraction → rule derivation → compile → confidence.

    Returns a single dict capturing every intermediate stage (the reviewer's requested
    reasoning chain). ``exclude_titles`` withholds source documents for held-out tests.
    """
    store = RAGStore(db_path)
    client = LLMClient(config)

    passages = retrieve_passages(store, payload_class, limit=limit, exclude_titles=exclude_titles)
    exemplars, ex_ok = extract_exemplars(client, payload_class, passages)
    rule, rule_ok = derive_rule(client, payload_class, exemplars, passages)
    llm_ok = ex_ok and rule_ok and rule is not None
    objective = (compile_objective(rule, payload_class=payload_class, exemplars=exemplars)
                 if rule is not None else None)
    confidence = rule_confidence(rule, exemplars, passages)

    return {
        "payload_class": payload_class,
        "query": PAYLOAD_QUERIES.get(payload_class, ""),
        "withheld": list(exclude_titles or []),
        "passages": passages,
        "n_passages": len(passages),
        "exemplars": exemplars,
        "rule": rule,
        "objective": objective,
        "confidence": confidence,
        "llm_ok": llm_ok,
        "abstained": rule is None,
    }
