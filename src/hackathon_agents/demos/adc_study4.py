"""Study 4 demo harness — the reasoning made visible + the held-out prediction.

Two entry points:

* ``run_phase1_reasoning`` — runs the grounded literature reasoning chain for all three
  payload classes on the full corpus and writes ``reasoning_chains.json`` (the artifact
  behind the paper's "reasoning waterfall" figure — CRITIQUE_S3 #1).

* ``run_phase2_heldout`` — leave-one-paper-out (CRITIQUE_S3 #2/#3, the central experiment):
  for each class it withholds that class's key paper, re-derives the rule from the
  *remaining* corpus, records the prediction + confidence, then reveals the withheld
  paper's stated conclusion and scores agree / disagree / abstain.

Honesty guards: predictions come only from genuine LLM output (``llm_ok``); a failed call
is an *abstain*, never a planted default. The withheld paper's passages are excluded at
retrieval, so the agent never sees the paper it is tested against.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hackathon_agents.config import load_config
from hackathon_agents.logging_config import configure_logging, get_logger
from hackathon_agents.tools.lit_reasoning_s4 import (
    build_reasoning_chain,
    normalize_rule,
)

logger = get_logger(__name__)

PAYLOAD_CLASSES = ["cytotoxin", "oligonucleotide", "immunomodulator"]

# Ground truth for the held-out test = the withheld paper's stated design conclusion.
# `expected_cleavage` is in canonical scorer terms (reward = keep cleavable;
# penalize = prefer non-cleavable). These are the conclusions the agent must reach
# WITHOUT having read the withheld paper.
WITHHELD_TRUTH: dict[str, dict[str, Any]] = {
    "cytotoxin": {
        "withhold": ["biomedicines-11-03080"],
        "expected_cleavage": "reward",
        "expected_stability": {"standard", "high", "paramount"},
        "statement": (
            "Lysosomal cathepsin-B-cleavable Val-Cit/Val-Ala peptide linkers enable "
            "traceless intracellular release of the cytotoxin (Balamkundu & Liu, "
            "Biomedicines 2023)."
        ),
        "surprising": False,
    },
    "immunomodulator": {
        "withhold": ["Immuno"],
        "expected_cleavage": "reward",
        "expected_stability": {"paramount"},
        "statement": (
            "Imidazoquinoline TLR7/8 ISAC linkers may be cleavable to release the agonist "
            "in the tumour, but demand maximal plasma stability to avoid systemic cytokine "
            "toxicity (imidazo[4,5-c]quinoline ISAC paper)."
        ),
        "surprising": False,
    },
    "oligonucleotide": {
        "withhold": ["siRNA"],
        "expected_cleavage": "penalize",
        "expected_stability": {"high", "paramount"},
        "statement": (
            "Antibody-siRNA conjugates favour a rigid, NON-cleavable linker (sulfo-SMCC); "
            "a cleavable linker that prematurely sheds the polyanionic oligonucleotide is a "
            "liability (ARC paper, Bioconjugate Chem. 2025)."
        ),
        "surprising": True,  # the non-default conclusion — the showcase
    },
}


def _score_heldout(chain: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    """Compare the blind prediction to the withheld paper's conclusion."""
    if chain.get("abstained") or not chain.get("llm_ok") or chain.get("rule") is None:
        return {"verdict": "abstain", "reason": "LLM abstained / no rule derived"}
    canon = normalize_rule(chain["rule"])
    predicted_cleave = canon["cleavage_preference"]
    predicted_stab = canon["stability_priority"]
    cleave_match = predicted_cleave == truth["expected_cleavage"]
    stab_match = predicted_stab in truth["expected_stability"]
    verdict = "agree" if cleave_match else "disagree"
    return {
        "verdict": verdict,
        "predicted_cleavage": predicted_cleave,
        "expected_cleavage": truth["expected_cleavage"],
        "cleavage_match": cleave_match,
        "predicted_stability": predicted_stab,
        "stability_match": stab_match,
    }


def run_phase1_reasoning(
    out_dir: str | Path = "deliverables/study4",
    db_path: str | Path = "data/rag.sqlite",
    *,
    limit: int = 10,
) -> dict[str, Any]:
    configure_logging()
    config = load_config(env_file=".env")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    chains: dict[str, Any] = {}
    for pc in PAYLOAD_CLASSES:
        logger.info("Phase 1 reasoning chain: %s", pc)
        chain = build_reasoning_chain(pc, config, db_path=db_path, limit=limit)
        rule = chain.get("rule") or {}
        conf = chain.get("confidence", {})
        logger.info(
            "  %s -> cleavage=%s rigidity=%s stability=%s | conf=%.2f (%s) | %d passages, %d/%d grounded exemplars | llm_ok=%s",
            pc, rule.get("cleavage_preference"), rule.get("rigidity"), rule.get("stability_priority"),
            conf.get("score", 0.0), conf.get("label"), chain.get("n_passages", 0),
            conf.get("n_grounded", 0), conf.get("n_exemplars", 0), chain.get("llm_ok"),
        )
        chains[pc] = chain

    path = out / "reasoning_chains.json"
    path.write_text(json.dumps(chains, indent=2))
    logger.info("Wrote %s", path)
    return chains


def run_phase2_heldout(
    out_dir: str | Path = "deliverables/study4",
    db_path: str | Path = "data/rag.sqlite",
    *,
    limit: int = 10,
) -> dict[str, Any]:
    configure_logging()
    config = load_config(env_file=".env")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {}
    for pc, truth in WITHHELD_TRUTH.items():
        logger.info("Phase 2 held-out: %s (withholding %s)", pc, truth["withhold"])
        chain = build_reasoning_chain(
            pc, config, db_path=db_path, limit=limit, exclude_titles=truth["withhold"]
        )
        # Verify the withheld paper truly never entered the context.
        seen_sources = {p["source"] for p in chain.get("passages", [])}
        leaked = seen_sources.intersection({s.lower() for s in truth["withhold"]})
        score = _score_heldout(chain, truth)
        rule = chain.get("rule") or {}
        conf = chain.get("confidence", {})
        logger.info(
            "  %s -> predicted cleavage=%s (expected %s) => %s | conf=%.2f | leaked=%s",
            pc, score.get("predicted_cleavage"), truth["expected_cleavage"],
            score["verdict"], conf.get("score", 0.0), bool(leaked),
        )
        results[pc] = {
            "withheld": truth["withhold"],
            "leaked_sources": sorted(leaked),
            "surprising": truth["surprising"],
            "prediction": {
                "cleavage_preference": rule.get("cleavage_preference"),
                "rigidity": rule.get("rigidity"),
                "stability_priority": rule.get("stability_priority"),
                "rationale": rule.get("rationale"),
                "self_confidence": rule.get("self_confidence"),
            },
            "confidence": conf,
            "n_passages": chain.get("n_passages", 0),
            "sources_seen": sorted(seen_sources),
            "withheld_paper_conclusion": truth["statement"],
            "score": score,
            "llm_ok": chain.get("llm_ok"),
            "full_chain": chain,
        }

    path = out / "heldout_predictions.json"
    path.write_text(json.dumps(results, indent=2))
    logger.info("Wrote %s", path)

    # Console summary
    print("\n=== LEAVE-ONE-PAPER-OUT SUMMARY ===")
    for pc, r in results.items():
        s = r["score"]
        tag = "SURPRISING" if r["surprising"] else "sanity"
        print(f"[{tag:10s}] {pc:16s} withhold={r['withheld']!s:28s} "
              f"predicted={s.get('predicted_cleavage','-'):18s} expected={s.get('expected_cleavage','-') if 'expected_cleavage' in s else '-':10s} "
              f"=> {s['verdict'].upper():8s} (conf {r['confidence'].get('score',0):.2f}, leaked={bool(r['leaked_sources'])})")
    return results


if __name__ == "__main__":
    import sys
    phase = sys.argv[1] if len(sys.argv) > 1 else "1"
    if phase == "2":
        run_phase2_heldout()
    else:
        run_phase1_reasoning()
