"""Study 4 — payload-rule-matched actionable shortlist (CRITIQUE_S3 #4).

Turns the raw grid pool (hundreds of designs ranked purely on the composite) into a
small, chemist-facing shortlist: for each payload class, the top designs that ALSO
respect that class's literature-derived cleavage rule (cleavable for cytotoxin/ISAC,
non-cleavable for oligonucleotide), each annotated with retrosynthetic step count,
mechanism-resolved stability, and the assembled handle-linker-payload construct.

This is the substrate for the structure gallery (Phase 5) and the dossiers (Phase 6).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rdkit import Chem

from hackathon_agents.tools.adc_linker_objective import CLEAVABLE_MOTIF_SMARTS
from hackathon_agents.tools.predictive_scorers import (
    estimate_retrosynthetic_steps,
    score_mechanism_resolved_stability,
)
from hackathon_agents.tools.real_payloads import PAYLOADS, assemble_construct

# payload class -> representative real payload key
CLASS_TO_PAYLOAD = {
    "cytotoxin": "MMAE",
    "oligonucleotide": "siRNA",
    "immunomodulator": "R848",
}
# Per-class selection constraints, grounded in the literature-derived rule:
#   cytotoxin  -> reward cleavable release (require a cleavable motif)
#   oligo      -> penalise cleavage; rigid non-cleavable (forbid cleavable motif)
#   immuno     -> cleavage optional but plasma stability is PARAMOUNT (require high stab)
# `wants_cleavable=None` means "no cleavage constraint".
CLASS_CONSTRAINTS: dict[str, dict[str, Any]] = {
    "cytotoxin": {"wants_cleavable": True, "min_stability": 0.6},
    "oligonucleotide": {"wants_cleavable": False, "min_stability": 0.6},
    # ISAC wants high plasma stability; 0.8 admits the standard maleimide handle
    # (0.85, deconjugation liability reported honestly) but rejects hydrolytic linkers.
    "immunomodulator": {"wants_cleavable": None, "min_stability": 0.8},
}
_DEFAULT_CONSTRAINT = {"wants_cleavable": True, "min_stability": 0.6}

_CLEAVABLE_QUERIES = [Chem.MolFromSmarts(s) for s in CLEAVABLE_MOTIF_SMARTS]


def has_cleavable_motif(smiles: str) -> bool:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return False
    return any(q is not None and mol.HasSubstructMatch(q) for q in _CLEAVABLE_QUERIES)


def _pool(grid: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten + dedupe grid candidates by SMILES, keeping the best-scoring copy."""
    seen: dict[str, dict[str, Any]] = {}
    for rec in grid.get("records", []):
        payload = rec.get("payload", "cytotoxin")
        for cand in rec.get("top", []):
            smi = cand.get("smiles")
            if not smi:
                continue
            key = f"{payload}::{smi}"
            entry = {
                **cand,
                "handle": rec.get("handle"),
                "trigger": rec.get("trigger"),
                "payload": payload,
                "seed": rec.get("seed"),
            }
            if key not in seen or (cand.get("score") or 0) > (seen[key].get("score") or 0):
                seen[key] = entry
    return list(seen.values())


def select_shortlist(
    grid_path: str | Path,
    *,
    per_class: int = 5,
) -> dict[str, Any]:
    grid = json.loads(Path(grid_path).read_text())
    pool = _pool(grid)

    by_class: dict[str, list[dict[str, Any]]] = {}
    for c in pool:
        by_class.setdefault(c["payload"], []).append(c)

    shortlist: dict[str, list[dict[str, Any]]] = {}
    for payload_class, cands in by_class.items():
        constraint = CLASS_CONSTRAINTS.get(payload_class, _DEFAULT_CONSTRAINT)
        wants_cleavable = constraint["wants_cleavable"]
        min_stability = constraint["min_stability"]
        payload_key = CLASS_TO_PAYLOAD.get(payload_class)

        annotated: list[dict[str, Any]] = []
        for c in cands:
            smi = c["smiles"]
            cleavable = has_cleavable_motif(smi)
            # Enforce the class's cleavage rule (when it has one).
            if wants_cleavable is not None and cleavable != wants_cleavable:
                continue
            retro = estimate_retrosynthetic_steps(smi)
            stab = score_mechanism_resolved_stability(smi)
            # Reject unsynthesisable (>7 steps) and insufficiently stable designs.
            if not retro.get("is_feasible") or stab.get("overall_stability_score", 0) < min_stability:
                continue
            construct = assemble_construct(smi, payload_key) if payload_key else {}
            annotated.append({
                "smiles": smi,
                "handle": c.get("handle"),
                "trigger": c.get("trigger"),
                "payload_class": payload_class,
                "real_payload": payload_key,
                "composite_score": c.get("score"),
                "subscores": c.get("subscores"),
                "has_cleavable_motif": cleavable,
                "retrosynthesis": retro,
                "stability": stab,
                "assembled_construct": {
                    "assembled_smiles": construct.get("assembled_smiles"),
                    "target_dar": construct.get("target_dar"),
                    "conjugation_site": construct.get("conjugation_site"),
                    "descriptors": construct.get("descriptors"),
                },
            })

        annotated.sort(key=lambda x: (x.get("composite_score") or 0), reverse=True)
        # dedupe near-identical SMILES already handled by _pool; take top N
        shortlist[payload_class] = annotated[:per_class]

    total = sum(len(v) for v in shortlist.values())
    return {
        "grid_path": str(grid_path),
        "per_class": per_class,
        "counts": {k: len(v) for k, v in shortlist.items()},
        "total": total,
        "shortlist": shortlist,
    }


def _annotate(smi: str, payload_class: str, handle: str, trigger: str, score, subscores) -> dict[str, Any] | None:
    """Annotate a design with retro/stability/construct; None if it fails the med-chem gate."""
    constraint = CLASS_CONSTRAINTS.get(payload_class, _DEFAULT_CONSTRAINT)
    cleavable = has_cleavable_motif(smi)
    if constraint["wants_cleavable"] is not None and cleavable != constraint["wants_cleavable"]:
        return None
    retro = estimate_retrosynthetic_steps(smi)  # reported as a complexity index, NOT a hard gate
    stab = score_mechanism_resolved_stability(smi)
    # Gate on the mechanism-stability score only. We deliberately do NOT hard-filter on the
    # step-count heuristic: it over-penalises amide-rich peptidic linkers (e.g. Val-Cit-PABC,
    # a clinically standard linker), so it survives only as a reported diagnostic. The
    # continuous SA_Score already down-weights genuinely hard synthesis in the composite.
    if stab.get("overall_stability_score", 0) < constraint["min_stability"]:
        return None
    payload_key = CLASS_TO_PAYLOAD.get(payload_class)
    construct = assemble_construct(smi, payload_key) if payload_key else {}
    return {
        "smiles": smi, "handle": handle, "trigger": trigger, "payload_class": payload_class,
        "real_payload": payload_key, "composite_score": score, "subscores": subscores,
        "has_cleavable_motif": cleavable, "retrosynthesis": retro, "stability": stab,
        "assembled_construct": {"assembled_smiles": construct.get("assembled_smiles"),
                                "target_dar": construct.get("target_dar"),
                                "conjugation_site": construct.get("conjugation_site"),
                                "descriptors": construct.get("descriptors")},
    }


def select_from_generated(designs_path: str | Path, *, per_class: int = 5) -> dict[str, Any]:
    """Select the shortlist from FRESHLY GENERATED designs (Study 5, closes IV.1).

    Unlike ``select_shortlist`` (which re-ranked a cached grid pool), this consumes
    ``generated_designs.json`` produced by REINVENT under each class's *compiled* objective,
    so the shortlist molecules were actually generated by the derived rule.
    """
    data = json.loads(Path(designs_path).read_text())
    shortlist: dict[str, list[dict[str, Any]]] = {}
    for payload_class, rec in data.items():
        seen: set[str] = set()
        annotated: list[dict[str, Any]] = []
        for cand in rec.get("top", []):
            smi = cand.get("smiles")
            if not smi or smi in seen:
                continue
            seen.add(smi)
            a = _annotate(smi, payload_class, rec.get("handle"), rec.get("trigger"),
                          cand.get("score"), cand.get("subscores"))
            if a:
                annotated.append(a)
        annotated.sort(key=lambda x: (x.get("composite_score") or 0), reverse=True)
        shortlist[payload_class] = annotated[:per_class]
    return {"designs_path": str(designs_path), "per_class": per_class,
            "counts": {k: len(v) for k, v in shortlist.items()},
            "total": sum(len(v) for v in shortlist.values()),
            "generated": True, "shortlist": shortlist}


def write_shortlist_from_generated(
    designs_path: str | Path = "deliverables/study5/generated_designs.json",
    out_path: str | Path = "deliverables/study5/shortlist.json",
    *, per_class: int = 5,
) -> dict[str, Any]:
    result = select_from_generated(designs_path, per_class=per_class)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(result, indent=2))
    return result


def write_shortlist(
    grid_path: str | Path,
    out_path: str | Path = "deliverables/study4/shortlist.json",
    *,
    per_class: int = 5,
) -> dict[str, Any]:
    result = select_shortlist(grid_path, per_class=per_class)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    r = write_shortlist("deliverables/study3/grid_results.json")
    print("shortlist counts:", r["counts"], "total", r["total"])
    for cls, items in r["shortlist"].items():
        print(f"\n=== {cls} ===")
        for it in items:
            print(f"  score={it['composite_score']:.3f} steps={it['retrosynthesis']['step_count']} "
                  f"stab={it['stability']['overall_stability_score']} cleavable={it['has_cleavable_motif']} "
                  f"handle={it['handle']}/{it['trigger']}")
            print(f"    {it['smiles']}")
