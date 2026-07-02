"""Disagreement-aware confidence + evidence composition (Reviewer 2, Part V.1).

The Study-5 confidence rewarded evidence *volume* (n_grounded) but ignored evidence
*consensus*: the ARC held-out derived a single cleavable rule at 0.81 even though its
grounded exemplars genuinely split (Val-Cit / Val-Arg / disulfide cleavable vs SMCC /
non-cleavable-maleimide). A contested field should drive confidence *down* and be flagged.

This module computes, from the grounded exemplars already in the shipped JSON (no re-run):
  * evidence composition — fraction favouring cleavable vs non-cleavable;
  * a disagreement-aware confidence — strong only when evidence is both plentiful AND
    consistent; contested evidence caps it;
  * a `contested` flag + a minority report (the dissenting exemplars).
"""

from __future__ import annotations

from typing import Any


def _cleave_class(exemplar: dict[str, Any]) -> str | None:
    """Classify a grounded exemplar as 'cleavable' / 'non-cleavable' / None (unspecified)."""
    c = str(exemplar.get("cleavage", "")).lower()
    if not c or c == "unspecified":
        return None
    if "non-cleavable" in c or "noncleavable" in c:
        return "non-cleavable"
    if "cleavable" in c:  # protease-, acid-, disulfide-cleavable all count as cleavable release
        return "cleavable"
    return None


def evidence_composition(exemplars: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the cleavable/non-cleavable breakdown of the grounded exemplars."""
    grounded = [e for e in exemplars if e.get("grounded")]
    labels = [_cleave_class(e) for e in grounded]
    n_cleave = labels.count("cleavable")
    n_non = labels.count("non-cleavable")
    n_spec = n_cleave + n_non
    n_unspec = labels.count(None)
    modal = "cleavable" if n_cleave >= n_non else "non-cleavable"
    consensus = (max(n_cleave, n_non) / n_spec) if n_spec else 0.0
    minority = "non-cleavable" if modal == "cleavable" else "cleavable"
    minority_reports = [
        {"linker": e.get("linker"), "cleavage": e.get("cleavage"), "source": e.get("source")}
        for e, lab in zip(grounded, labels) if lab == minority
    ]
    return {
        "n_grounded": len(grounded),
        "n_cleavable": n_cleave,
        "n_non_cleavable": n_non,
        "n_unspecified": n_unspec,
        "cleavable_frac": round(n_cleave / n_spec, 3) if n_spec else 0.0,
        "modal": modal,
        "consensus": round(consensus, 3),
        "contested": (min(n_cleave, n_non) >= 2),
        "minority_report": minority_reports,
    }


def disagreement_aware_confidence(exemplars: list[dict[str, Any]], base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Confidence that is high only when evidence is plentiful AND consistent.

    confidence = evidence_strength x consensus_penalty
      evidence_strength = min(1, n_specified / 6)      (saturates ~6 labelled exemplars)
      consensus_penalty = clamp(2*consensus - 1, 0, 1) (1.0 unanimous, 0.5 -> 0)
    Contested evidence (>=2 on the minority side) therefore collapses confidence even when
    n_grounded is large -- the fix Reviewer 2 asked for.
    """
    comp = evidence_composition(exemplars)
    n_spec = comp["n_cleavable"] + comp["n_non_cleavable"]
    # Strength = how much grounded evidence there is (all grounded exemplars, not only
    # cleavage-labelled ones). Consensus = agreement among the cleavage-labelled subset.
    evidence_strength = min(1.0, comp["n_grounded"] / 6.0)
    consensus_penalty = max(0.0, min(1.0, 2.0 * comp["consensus"] - 1.0))
    score = round(min(0.97, evidence_strength * consensus_penalty), 3)
    # Contested only when there is enough labelled evidence to judge and a real minority.
    contested = (n_spec >= 3) and (comp["consensus"] < 0.7)
    comp["contested"] = contested
    label = "high" if score >= 0.7 else ("medium" if score >= 0.4 else "low")
    out = {
        "score": score,
        "label": label,
        "evidence_strength": round(evidence_strength, 3),
        "consensus": comp["consensus"],
        "contested": contested,
        "composition": comp,
    }
    # preserve a few legacy fields if a base confidence dict was passed
    if base:
        out["n_grounded"] = base.get("n_grounded", comp["n_grounded"])
        out["prev_score"] = base.get("score")
    return out


def annotate_chain(chain: dict[str, Any]) -> dict[str, Any]:
    """Return the chain's confidence recomputed to be disagreement-aware (non-mutating)."""
    exs = chain.get("exemplars", [])
    return disagreement_aware_confidence(exs, base=chain.get("confidence"))
