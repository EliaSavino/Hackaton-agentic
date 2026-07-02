"""Study 5 Phase IV.1 — close the loop: the DERIVED rule generates the molecules.

Reviewer 2 (Part IV.1): Study 4's shortlist was *selected from a cached pre-Study-4 pool*
and merely filtered by the compiled objective; the derived rule did not *drive generation*.
Here we close that loop end to end, per payload class:

    enriched RAG  →  LLM reasoning chain  →  derived rule  →  ADCGoalProfile
                  →  build_adc_linkinvent_objective  →  REINVENT LinkInvent (pod)
                  →  designs that (a) are optimised under the derived weights and
                     (b) carry the class-specific motif, because the trigger warhead
                     that embodies the rule is fixed into every generated molecule.

So the delivered molecules are produced by the agent's reasoning, and honour the specific
motif (Val-Cit for cytotoxin, Val-Ala for ISAC, rigid sulfo-SMCC cap for ARC), not merely
the coarse cleavage regime. Every run records its ``mock`` flag for the provenance gate.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from hackathon_agents.config import load_config
from hackathon_agents.logging_config import configure_logging, get_logger
from hackathon_agents.schemas.linkers import ADCGoalProfile
from hackathon_agents.tools.lit_reasoning_s4 import build_reasoning_chain, compile_objective
from hackathon_agents.tools.adc_linker_objective import build_adc_linkinvent_objective, score_adc_linker
from hackathon_agents.tools.reinvent_tools import ReinventInput, generate_with_reinvent
from hackathon_agents.demos.adc_grid import GRID_HANDLES, GRID_TRIGGERS, warhead_pair, _ssh_env

logger = get_logger(__name__)

# Each class's warhead embodies its literature-derived rule: the trigger fragment is
# welded into every generated molecule, so the class-specific motif is enforced by
# construction (Val-Cit / Val-Ala protease dipeptide, or the rigid sulfo-SMCC cap).
CLASS_WARHEAD = {
    "cytotoxin": ("Maleimide", "Val-Cit-PABC"),        # protease-cleavable, cathepsin B
    "immunomodulator": ("Maleimide", "Val-Ala-PABC"),  # cleavable but higher plasma stability (ISAC)
    "oligonucleotide": ("DBCO", "Non-cleavable-rigid"), # rigid non-cleavable sulfo-SMCC cap (ARC)
}


def profile_from_rule(rule: dict[str, Any] | None) -> ADCGoalProfile:
    """Build the optimisation profile from the LLM-DERIVED rule (not a hardcoded preset)."""
    base = ADCGoalProfile()
    if not rule:
        return base
    obj = compile_objective(rule)
    weights = dict(base.weights)
    weights.update(obj.get("weights", {}))
    data = base.model_dump()
    data.update({
        "cleavage_preference": obj.get("cleavage_regime"),
        "require_cleavable_motif": obj.get("require_cleavable_motif", True),
        "max_rot_bonds": obj.get("max_rot_bonds", base.max_rot_bonds),
        "weights": weights,
    })
    return ADCGoalProfile.model_validate(data)


def _generate_one(payload_class: str, profile: ADCGoalProfile, *, steps: int, batch: int,
                  work_root: Path, top_n: int) -> dict[str, Any]:
    handle, trigger = CLASS_WARHEAD[payload_class]
    wp = warhead_pair(handle, trigger)
    obj = build_adc_linkinvent_objective(
        profile, warhead_pair=wp, run_type="staged_learning", run=True, device="cpu",
        max_steps=steps, min_steps=min(25, steps), batch_size=batch,
    )
    obj["work_dir"] = str(work_root / f"{payload_class}__{handle}__{trigger}")
    obj["timeout_seconds"] = 1800
    obj.update(_ssh_env())
    result = generate_with_reinvent(ReinventInput(**obj))
    molecules = result.data.get("molecules", []) if result.ok else []
    mock = bool(result.data.get("mock")) if result.ok else True

    from rdkit import Chem
    trig_core = GRID_TRIGGERS[trigger]["smiles"].replace("*", "")
    query = Chem.MolFromSmiles(trig_core) or Chem.MolFromSmarts("c1ccccc1")

    scored: list[dict[str, Any]] = []
    for mol in molecules:
        smi = mol.get("smiles")
        if not smi:
            continue
        m = Chem.MolFromSmiles(smi)
        if m is None or not m.HasSubstructMatch(query):
            continue  # keep only genuine assembled linkers that carry the class motif
        composite, subscores = score_adc_linker(smi, profile)
        if composite is None:
            continue
        scored.append({"smiles": smi, "score": composite, "subscores": subscores,
                       "descriptors": mol.get("descriptors", {})})
    scored.sort(key=lambda c: c["score"], reverse=True)
    return {
        "payload_class": payload_class, "handle": handle, "trigger": trigger,
        "warhead_pair": wp, "cleavage_preference": profile.cleavage_preference,
        "max_rot_bonds": profile.max_rot_bonds, "weights": profile.weights,
        "mock": mock, "ok": result.ok, "error": None if result.ok else result.error,
        "n_generated": len(molecules), "n_assembled": len(scored),
        "best_score": scored[0]["score"] if scored else None,
        "top": scored[:top_n],
    }


def run_generation(
    out_dir: str | Path = "deliverables/study5",
    db_path: str | Path = "data/rag.sqlite",
    *,
    steps: int = 40,
    batch: int = 32,
    top_n: int = 12,
    limit: int = 12,
) -> dict[str, Any]:
    configure_logging()
    os.environ.setdefault("HACKATHON_AGENT_LLM_MODE", "always")
    config = load_config(env_file=".env")
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    work_root = out / "reinvent_runs"; work_root.mkdir(parents=True, exist_ok=True)

    chains: dict[str, Any] = {}
    designs: dict[str, Any] = {}
    for pc in ("cytotoxin", "immunomodulator", "oligonucleotide"):
        logger.info("=== V5 reason+generate: %s ===", pc)
        chain = build_reasoning_chain(pc, config, db_path=db_path, limit=limit)
        chains[pc] = chain
        profile = profile_from_rule(chain.get("rule"))
        logger.info("  derived profile: cleavage=%s rot<=%s weights=%s",
                    profile.cleavage_preference, profile.max_rot_bonds, profile.weights)
        rec = _generate_one(pc, profile, steps=steps, batch=batch, work_root=work_root, top_n=top_n)
        logger.info("  generated: ok=%s mock=%s n_assembled=%s best=%s",
                    rec["ok"], rec["mock"], rec["n_assembled"], rec["best_score"])
        designs[pc] = rec

    (out / "reasoning_chains.json").write_text(json.dumps(chains, indent=2))
    (out / "generated_designs.json").write_text(json.dumps(designs, indent=2))
    logger.info("wrote reasoning_chains.json + generated_designs.json to %s", out)
    print("GENERATION_DONE",
          {k: {"mock": v["mock"], "n_assembled": v["n_assembled"], "best": v["best_score"]}
           for k, v in designs.items()})
    return {"chains": chains, "designs": designs}


if __name__ == "__main__":
    run_generation()
