"""Study 4 — experimentally actionable candidate dossiers (CRITIQUE_S3 #4, #8).

For each shortlisted design, produce a chemist-facing dossier that combines deterministic
predictions (retrosynthetic step count, mechanism-resolved stability, nearest commercial
analogue by Morgan-Tanimoto, and cost/duration/probability-of-success estimates derived
from them) with an LLM-written narrative (design rationale traced to the derived rule,
a short synthesis route, expected failure modes, and recommended validation experiments).

The rationale is *traced to the literature-derived rule* (from Phase 1), so a chemist can
audit why the agent proposed each molecule — not just that it scored well.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs

from hackathon_agents.config import load_config
from hackathon_agents.llm.client import LLMClient, CompletionRequest
from hackathon_agents.logging_config import configure_logging, get_logger
from hackathon_agents.tools.linker_benchmark import COMMERCIAL_LINKERS
from hackathon_agents.tools.lit_reasoning_s4 import _extract_json

logger = get_logger(__name__)


def _fp(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)


_COMMERCIAL_FPS = [(x, _fp(x["smiles"])) for x in COMMERCIAL_LINKERS]


def closest_analogue(smiles: str) -> dict[str, Any]:
    fp = _fp(smiles)
    if fp is None:
        return {"name": None, "tanimoto": 0.0}
    best, best_t = None, -1.0
    for x, xfp in _COMMERCIAL_FPS:
        if xfp is None:
            continue
        t = DataStructs.TanimotoSimilarity(fp, xfp)
        if t > best_t:
            best, best_t = x, t
    if best is None:
        return {"name": None, "tanimoto": 0.0}
    return {"name": best["name"], "smiles": best["smiles"], "class": best.get("class"),
            "adc": best.get("adc"), "tanimoto": round(best_t, 3)}


def _economics(retro: dict[str, Any], stability: dict[str, Any]) -> dict[str, Any]:
    """Rough experimental-prioritisation estimates from step count + stability."""
    steps = int(retro.get("step_count", 8))
    retro_score = float(retro.get("score", 0.3))
    stab = float(stability.get("overall_stability_score", 0.5))
    est_cost_usd = int(round(350 * steps + 250, -2))        # building blocks + reagents, order-of-mag
    est_duration_days = round(2.5 * steps, 1)               # bench time, rough
    p_success = round(min(0.95, max(0.05, retro_score * (0.6 + 0.4 * stab))), 2)
    return {
        "estimated_synthesis_steps": steps,
        "estimated_cost_usd": est_cost_usd,
        "estimated_duration_days": est_duration_days,
        "probability_of_success": p_success,
        "note": "order-of-magnitude heuristics from step count + stability; not a quote",
    }


def _narrative(client: LLMClient, cand: dict[str, Any], rule: dict[str, Any] | None,
               analogue: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    rule_txt = json.dumps({
        "cleavage_preference": (rule or {}).get("cleavage_preference"),
        "rigidity": (rule or {}).get("rigidity"),
        "stability_priority": (rule or {}).get("stability_priority"),
        "rationale": (rule or {}).get("rationale"),
    }, indent=2)
    prompt = f"""You are an ADC medicinal chemist writing a candidate dossier. Be concise and concrete.

Payload class: {cand['payload_class']} (real payload: {cand.get('real_payload')})
Designed linker SMILES: {cand['smiles']}
Conjugation handle / trigger context: {cand.get('handle')} / {cand.get('trigger')}
Composite score: {cand.get('composite_score')}
Retro step estimate: {cand['retrosynthesis'].get('step_count')} steps ({cand['retrosynthesis'].get('reason')})
Stability: score {cand['stability'].get('overall_stability_score')}, liabilities {cand['stability'].get('liabilities')}
Nearest clinical analogue: {analogue.get('name')} (Tanimoto {analogue.get('tanimoto')}, from {analogue.get('adc')})

The literature-DERIVED design rule for this payload class (from the agent's Phase-1 reasoning) is:
{rule_txt}

Write a JSON dossier with EXACTLY these keys:
- "design_rationale": 2-3 sentences explaining why THIS molecule fits the derived rule for this payload class (reference the cleavage/rigidity/stability logic explicitly).
- "synthesis_route": a list of 3-6 short strings, each one synthetic step (name the coupling/reaction, e.g. "amide coupling of X with Y (HATU)").
- "expected_failure_modes": a list of 2-4 short strings (chemistry/stability/PK liabilities specific to this structure).
- "validation_experiments": a list of 2-4 short strings (concrete assays: e.g. "cathepsin B cleavage LC-MS", "plasma stability t1/2", "DAR by HIC").
- "information_gain": one sentence — what a chemist would LEARN by making and testing this, relative to the payload hypothesis.

Output raw JSON only."""
    resp = client.complete(CompletionRequest(
        model_alias="science_reasoning",
        messages=[
            {"role": "system", "content": "You are a precise ADC medicinal chemist. Output raw JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2, max_tokens=900,
    ))
    if not resp.ok:
        return {}, False
    try:
        return _extract_json(resp.content), True
    except Exception:
        return {}, False


def build_dossier(client: LLMClient, cand: dict[str, Any], rule: dict[str, Any] | None) -> dict[str, Any]:
    analogue = closest_analogue(cand["smiles"])
    econ = _economics(cand["retrosynthesis"], cand["stability"])
    narrative, ok = _narrative(client, cand, rule, analogue)
    return {
        "payload_class": cand["payload_class"],
        "real_payload": cand.get("real_payload"),
        "smiles": cand["smiles"],
        "assembled_smiles": (cand.get("assembled_construct") or {}).get("assembled_smiles"),
        "handle": cand.get("handle"),
        "trigger": cand.get("trigger"),
        "composite_score": cand.get("composite_score"),
        "subscores": cand.get("subscores"),
        "has_cleavable_motif": cand.get("has_cleavable_motif"),
        "retrosynthesis": cand["retrosynthesis"],
        "stability": cand["stability"],
        "closest_analogue": analogue,
        "economics": econ,
        "narrative": narrative,
        "narrative_llm_ok": ok,
    }


def run_dossiers(
    shortlist_path: str | Path = "deliverables/study4/shortlist.json",
    reasoning_path: str | Path = "deliverables/study4/reasoning_chains.json",
    out_path: str | Path = "deliverables/study4/dossiers.json",
) -> dict[str, Any]:
    configure_logging()
    config = load_config(env_file=".env")
    client = LLMClient(config)

    shortlist = json.loads(Path(shortlist_path).read_text())["shortlist"]
    chains = json.loads(Path(reasoning_path).read_text())

    dossiers: dict[str, list[dict[str, Any]]] = {}
    for payload_class, cands in shortlist.items():
        rule = (chains.get(payload_class) or {}).get("rule")
        out_list = []
        for i, cand in enumerate(cands):
            logger.info("dossier %s #%d ...", payload_class, i + 1)
            d = build_dossier(client, cand, rule)
            d["derived_rule"] = {
                "cleavage_preference": (rule or {}).get("cleavage_preference"),
                "rigidity": (rule or {}).get("rigidity"),
                "stability_priority": (rule or {}).get("stability_priority"),
                "confidence": (chains.get(payload_class) or {}).get("confidence", {}).get("score"),
            }
            out_list.append(d)
        dossiers[payload_class] = out_list

    result = {"dossiers": dossiers, "counts": {k: len(v) for k, v in dossiers.items()}}
    Path(out_path).write_text(json.dumps(result, indent=2))
    logger.info("wrote %s (%s)", out_path, result["counts"])
    return result


if __name__ == "__main__":
    r = run_dossiers()
    print("dossier counts:", r["counts"])
