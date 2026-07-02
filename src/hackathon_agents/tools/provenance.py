"""Provenance gate (Reviewer 2, Part I.6 / IV.6).

Every value that reaches the manuscript is tagged with a source so a mock/default
constant can never masquerade as a result:

    measured  — from a real predictive-model *run* (Boltz co-fold, REINVENT generation)
    llm       — from an actual LLM completion (llm_ok True)
    heuristic — a deterministic formula / cheminformatics computation (SA, stability,
                retro step count, Tanimoto, the confidence blend)
    mock      — a fallback / hardcoded default constant (the thing we must never ship)

The paper builder calls ``assert_no_mock_in_results`` before emitting any results claim
and renders ``provenance_rows`` as a table in the supplementary. This makes the honesty
guard enforced in code, not just asserted in prose.
"""

from __future__ import annotations

from typing import Any

# The exact fallback constants substituted by boltz_tools.run_boltz_2 when it cannot
# parse a real prediction (see _run_boltz_ssh). Any record carrying BOTH is mock.
_MOCK_BOLTZ_IPTM = 0.82
_MOCK_BOLTZ_KD = 12.4


class ProvenanceError(AssertionError):
    """Raised when a mock/default value would reach a results claim."""


def boltz_source(rec: dict[str, Any]) -> str:
    """Classify a Boltz co-fold record."""
    if not rec.get("ok", False):
        return "mock"
    status = str(rec.get("status") or "").lower()
    if status == "mock":
        return "mock"
    iptm = rec.get("iptm")
    kd = rec.get("binding_affinity_kd_nm")
    if iptm is None or kd is None:
        return "mock"
    # Fingerprint of the hardcoded fallback constants.
    if abs(float(iptm) - _MOCK_BOLTZ_IPTM) < 1e-9 and abs(float(kd) - _MOCK_BOLTZ_KD) < 1e-9:
        return "mock"
    return "measured"


def design_source(rec: dict[str, Any]) -> str:
    """Classify a REINVENT generation record."""
    if not rec.get("ok", False):
        return "mock"
    if rec.get("mock"):
        return "mock"
    if not rec.get("n_assembled"):
        return "mock"
    return "measured"


def chain_source(chain: dict[str, Any]) -> str:
    """Classify a literature-reasoning chain (rule derivation)."""
    if chain.get("abstained") or not chain.get("llm_ok"):
        # An abstain is honest (not mock) *iff* it reports no rule; a rule produced
        # without the LLM would be a hardcoded fallback — but lit_reasoning_s4 never
        # fabricates one, so llm_ok False + rule present should not occur.
        return "abstain" if chain.get("rule") is None else "mock"
    return "llm"


def build_ledger(
    chains: dict[str, Any],
    designs: dict[str, Any] | None,
    boltz: list[dict[str, Any]] | None,
    heldout: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Return provenance rows for every value the paper reports."""
    rows: list[dict[str, str]] = []

    for pc, ch in (chains or {}).items():
        rows.append({"item": f"{pc}: derived rule + confidence", "source": chain_source(ch),
                     "detail": f"{ch.get('confidence',{}).get('n_grounded',0)} grounded exemplars, "
                               f"conf {ch.get('confidence',{}).get('score','?')}"})

    for pc, d in (designs or {}).items():
        rows.append({"item": f"{pc}: REINVENT-generated designs", "source": design_source(d),
                     "detail": f"{d.get('n_assembled','?')} assembled, best {d.get('best_score','?')}"})

    for pc, h in (heldout or {}).items():
        s = "llm" if h.get("llm_ok") else "abstain"
        rows.append({"item": f"{pc}: held-out prediction", "source": s,
                     "detail": f"verdict {h.get('score',{}).get('verdict','?')}, "
                               f"conf {h.get('confidence',{}).get('score','?')}"})

    for rec in (boltz or []):
        rows.append({"item": f"Boltz {rec.get('label','?')}: ipTM/Kd", "source": boltz_source(rec),
                     "detail": f"ipTM {rec.get('iptm','?')}, Kd {rec.get('binding_affinity_kd_nm','?')} nM"})

    # Deterministic cheminformatics used in dossiers/shortlist.
    rows.append({"item": "Synthesizability (Ertl SA_Score)", "source": "heuristic",
                 "detail": "continuous SA_Score, reverse-sigmoid to [0,1]"})
    rows.append({"item": "Complexity index (step-count proxy)", "source": "heuristic",
                 "detail": "MW/chirality/ring/linkage formula; reported, not a route"})
    rows.append({"item": "Mechanism stability score", "source": "heuristic",
                 "detail": "SMARTS liabilities: peptide/disulfide/maleimide/hydrolysis"})
    rows.append({"item": "Nearest clinical analogue (Tanimoto)", "source": "heuristic",
                 "detail": "Morgan fingerprint vs commercial linker set"})
    return rows


def assert_no_mock_in_results(rows: list[dict[str, str]]) -> None:
    """Raise if any results-bearing value is tagged ``mock``."""
    bad = [r for r in rows if r["source"] == "mock"]
    if bad:
        items = "; ".join(r["item"] for r in bad)
        raise ProvenanceError(
            f"Provenance gate: {len(bad)} value(s) trace to a mock/default constant and "
            f"cannot appear as results: {items}"
        )
