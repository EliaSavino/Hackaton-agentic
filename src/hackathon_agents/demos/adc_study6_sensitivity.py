"""Study 6 confidence stress-test (Reviewer, V9).

The disagreement-aware confidence is the paper's differentiator, so it must be robust, not
asserted. We perturb the retrieval---vary top-k and drop a retrieved source (jackknife)---
re-derive the grounded exemplars for each class, and recompute confidence. If the robust
classes (cytotoxin, ISAC) stay high and the contested class (ARC held-out) stays low/contested
across perturbations, the calibration claim is a reproducible behaviour, not a lucky number.

Only the exemplar-extraction LLM call is needed per condition (confidence + direction are
computed from the grounded exemplars), so this is light: a handful of extractions per class.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hackathon_agents.config import load_config
from hackathon_agents.logging_config import configure_logging, get_logger
from hackathon_agents.rag import RAGStore
from hackathon_agents.llm.client import LLMClient
from hackathon_agents.tools.lit_reasoning_s4 import retrieve_passages, extract_exemplars
from hackathon_agents.tools.consensus import disagreement_aware_confidence

logger = get_logger(__name__)

# The ARC case is evaluated in its held-out (contested) condition -- the siRNA showcase
# withheld -- so the stress-test asks: does ARC stay contested under perturbation?
ARC_WITHHELD = ["siRNA", "exploring-the-potentials-of-antibody-sirna-conjugates-in-tumor-cell-gene-silencing-without-cationic-assistance"]
CLASSES = [("cytotoxin", []), ("immunomodulator", []), ("oligonucleotide", ARC_WITHHELD)]
TOPK = [6, 8, 10, 12]


def _measure(store, client, payload_class, *, limit, exclude, drop_top=False) -> dict[str, Any]:
    passages = retrieve_passages(store, payload_class, limit=limit + (1 if drop_top else 0), exclude_titles=exclude)
    if drop_top and passages:
        passages = passages[1:]  # jackknife: drop the top-ranked retrieved passage
        for i, p in enumerate(passages, 1):
            p["idx"] = i
    exemplars, ok = extract_exemplars(client, payload_class, passages)
    conf = disagreement_aware_confidence(exemplars)
    comp = conf["composition"]
    return {"score": conf["score"], "consensus": conf["consensus"], "contested": conf["contested"],
            "modal": comp["modal"], "n_cleavable": comp["n_cleavable"], "n_non_cleavable": comp["n_non_cleavable"],
            "n_grounded": comp["n_grounded"], "llm_ok": ok}


def run_sensitivity(out_dir: str | Path = "deliverables/study6", db_path: str | Path = "data/rag.sqlite") -> dict[str, Any]:
    configure_logging()
    import os
    os.environ.setdefault("HACKATHON_AGENT_LLM_MODE", "always")
    config = load_config(env_file=".env")
    store = RAGStore(db_path)
    client = LLMClient(config)

    results: dict[str, Any] = {"topk": {}, "jackknife": {}}
    for payload_class, exclude in CLASSES:
        results["topk"][payload_class] = {}
        for k in TOPK:
            m = _measure(store, client, payload_class, limit=k, exclude=exclude)
            results["topk"][payload_class][k] = m
            logger.info("top-k sensitivity %s k=%d -> conf=%.2f modal=%s contested=%s (%d/%d)",
                        payload_class, k, m["score"], m["modal"], m["contested"], m["n_cleavable"], m["n_non_cleavable"])
        # jackknife: drop the top-ranked retrieved source at the default k
        mj = _measure(store, client, payload_class, limit=10, exclude=exclude, drop_top=True)
        results["jackknife"][payload_class] = mj
        logger.info("jackknife %s (drop top source) -> conf=%.2f contested=%s", payload_class, mj["score"], mj["contested"])

    # summary: does the behaviour hold across all perturbations?
    def _class_scores(pc):
        return [results["topk"][pc][k]["score"] for k in TOPK] + [results["jackknife"][pc]["score"]]
    summary = {}
    for pc, _ in CLASSES:
        s = _class_scores(pc)
        contesteds = [results["topk"][pc][k]["contested"] for k in TOPK] + [results["jackknife"][pc]["contested"]]
        summary[pc] = {"min": round(min(s), 3), "max": round(max(s), 3),
                       "always_high": all(x >= 0.6 for x in s), "always_contested": all(contesteds)}
    results["summary"] = summary

    Path(out_dir, "sensitivity.json").write_text(json.dumps(results, indent=2))
    print("\n=== CONFIDENCE STRESS-TEST SUMMARY ===")
    for pc, sm in summary.items():
        print(f"  {pc:16s} conf range [{sm['min']:.2f}, {sm['max']:.2f}]  always_high={sm['always_high']}  always_contested={sm['always_contested']}")
    return results


if __name__ == "__main__":
    run_sensitivity()
