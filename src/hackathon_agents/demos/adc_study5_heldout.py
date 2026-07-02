"""Study 5 held-out — the CONFIDENT recovery (Reviewer 2, IV.5).

V4's oligonucleotide held-out withheld the corpus's *only* ARC paper, so the agent
correctly abstained (confidence 0.007) — an uncertainty-calibration win, but not a
literature-derived recovery. With the enriched corpus (multiple ARC papers), we now
withhold the *showcase* siRNA paper(s) and test whether the agent recovers the rigid
non-cleavable rule from the OTHER, independent ARC papers. If it does with real
confidence, that is a genuine held-out scientific prediction.

Honesty preserved: predictions come only from genuine LLM output; the withheld papers'
passages never enter retrieval; we report whatever confidence actually results.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hackathon_agents.config import load_config
from hackathon_agents.logging_config import configure_logging, get_logger
from hackathon_agents.tools.lit_reasoning_s4 import build_reasoning_chain, normalize_rule

logger = get_logger(__name__)

# Withhold the primary siRNA/ARC showcase paper (+ its full-text duplicate) but KEEP the
# other ARC papers (SAR-of-ARC x2, thiol-ene oligo linkers, oligo metabolic stability),
# so recovery must come from independent ARC literature.
WITHHELD_V5: dict[str, dict[str, Any]] = {
    "cytotoxin": {
        "withhold": ["biomedicines-11-03080"],
        "expected_cleavage": "reward",
        "statement": "Lysosomal cathepsin-B-cleavable Val-Cit/Val-Ala peptide linkers enable traceless cytotoxin release.",
        "surprising": False,
    },
    "immunomodulator": {
        "withhold": ["Immuno"],
        "expected_cleavage": "reward",
        "statement": "TLR7/8 ISAC linkers may be cleavable but demand high plasma stability to avoid systemic cytokine toxicity.",
        "surprising": False,
    },
    "oligonucleotide": {
        "withhold": [
            "siRNA",
            "exploring-the-potentials-of-antibody-sirna-conjugates-in-tumor-cell-gene-silencing-without-cationic-assistance",
        ],
        "expected_cleavage": "penalize",
        "statement": "Antibody-oligonucleotide conjugates favour a rigid, NON-cleavable linker (sulfo-SMCC); a cleavable linker that sheds the polyanion is a liability.",
        "surprising": True,
    },
}


def _verdict(chain: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    if chain.get("abstained") or not chain.get("llm_ok") or chain.get("rule") is None:
        return {"verdict": "abstain", "predicted_cleavage": None, "expected_cleavage": truth["expected_cleavage"]}
    canon = normalize_rule(chain["rule"])
    pred = canon["cleavage_preference"]
    return {"verdict": "agree" if pred == truth["expected_cleavage"] else "disagree",
            "predicted_cleavage": pred, "expected_cleavage": truth["expected_cleavage"],
            "predicted_rigidity": canon["rigidity"]}


def run_heldout_v5(out_dir: str | Path = "deliverables/study5", db_path: str | Path = "data/rag.sqlite",
                   *, limit: int = 12) -> dict[str, Any]:
    configure_logging()
    import os
    os.environ.setdefault("HACKATHON_AGENT_LLM_MODE", "always")
    config = load_config(env_file=".env")
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {}
    for pc, truth in WITHHELD_V5.items():
        logger.info("V5 held-out: %s (withhold %s)", pc, truth["withhold"])
        chain = build_reasoning_chain(pc, config, db_path=db_path, limit=limit, exclude_titles=truth["withhold"])
        seen = {p["source"] for p in chain.get("passages", [])}
        leaked = sorted(seen.intersection({s.lower() for s in truth["withhold"]}))
        v = _verdict(chain, truth)
        rule = chain.get("rule") or {}
        conf = chain.get("confidence", {})
        logger.info("  %s -> pred=%s rigid=%s (expect %s) => %s | conf=%.2f leaked=%s | sources=%s",
                    pc, v.get("predicted_cleavage"), v.get("predicted_rigidity"), truth["expected_cleavage"],
                    v["verdict"], conf.get("score", 0.0), bool(leaked), sorted(seen))
        results[pc] = {
            "withheld": truth["withhold"], "leaked_sources": leaked, "surprising": truth["surprising"],
            "prediction": {"cleavage_preference": rule.get("cleavage_preference"),
                           "rigidity": rule.get("rigidity"), "stability_priority": rule.get("stability_priority"),
                           "rationale": rule.get("rationale"), "self_confidence": rule.get("self_confidence")},
            "confidence": conf, "n_passages": chain.get("n_passages", 0), "sources_seen": sorted(seen),
            "withheld_paper_conclusion": truth["statement"], "score": v, "llm_ok": chain.get("llm_ok"),
            "full_chain": chain,
        }

    (out / "heldout_predictions.json").write_text(json.dumps(results, indent=2))
    print("\n=== V5 HELD-OUT (confident recovery) ===")
    for pc, r in results.items():
        s = r["score"]
        print(f"[{'SHOWCASE' if r['surprising'] else 'sanity':8s}] {pc:16s} withhold={r['withheld']!s:70s} "
              f"pred={s.get('predicted_cleavage','-')}/{s.get('predicted_rigidity','-')} => {s['verdict'].upper()} "
              f"conf={r['confidence'].get('score',0):.2f} leaked={bool(r['leaked_sources'])}")
    return results


if __name__ == "__main__":
    run_heldout_v5()
