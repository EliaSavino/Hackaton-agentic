"""Multi-warhead ADC-linker design campaign.

Realises the full ADC vision: rather than optimising the linker for one fixed
warhead pair, we take the conjugation handles (Library A) and cleavable triggers
(Library B) distilled from a real linker corpus by
``tools/generate_linker_libraries.py`` and run the autonomous
generate -> score -> decide -> re-seed loop (``design-adc-linkers``) once per
warhead pair. Each campaign entry drives REINVENT LinkInvent to design the
tunable spacer *between* an antibody-side conjugation chemistry and a
protease-cleavable self-immolative trigger.

The per-pair runs are the existing ``run_demo`` pipeline (real LLM agents + real
REINVENT), so every pair gets its own escalation/reweighting decision trail. The
campaign then aggregates the winners across pairs into a single record that the
paper writer turns into a publication-shaped manuscript.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from hackathon_agents.config import RunMode
from hackathon_agents.demos.discovery_demo import run_demo
from hackathon_agents.logging_config import get_logger
from hackathon_agents.schemas.linkers import ADCGoalProfile, ADCStrategy

logger = get_logger(__name__)


# Conjugation handles (Library A) annotated with one LinkInvent attachment point
# where the designed spacer begins, plus the trigger fragments (Library B) with
# an attachment point at the peptide N-terminus (the self-immolative PAB benzylic
# alcohol is left free to couple the payload downstream).
CONJUGATION_HANDLES: dict[str, dict[str, str]] = {
    "Maleimide": {
        "smiles": "O=C1C=CC(=O)N1*",
        "chemistry": "cysteine thiol-Michael addition",
    },
    "DBCO": {
        "smiles": "*N1Cc2ccccc2C#Cc2ccccc21",
        "chemistry": "copper-free strain-promoted azide-alkyne click (SPAAC)",
    },
    "Disulfide": {
        "smiles": "*SSc1ccccn1",
        "chemistry": "pyridyl-disulfide exchange (redox-labile conjugation)",
    },
    "NHS_ester": {
        "smiles": "*C(=O)ON1C(=O)CCC1=O",
        "chemistry": "lysine amide coupling",
    },
}

CLEAVABLE_TRIGGERS: dict[str, dict[str, str]] = {
    "Val-Cit-PAB": {
        "smiles": "CC(C)[C@@H](C(=O)N[C@@H](CCCNC(=O)N)C(=O)Nc1ccc(CO)cc1)N*",
        "trigger": "cathepsin-B protease cleavage (self-immolative PAB)",
    },
    "Val-Ala-PAB": {
        "smiles": "CC(C)[C@@H](C(=O)N[C@@H](C)C(=O)Nc1ccc(CO)cc1)N*",
        "trigger": "cathepsin-B protease cleavage (Val-Ala, higher plasma stability)",
    },
}

# The curated campaign: four warhead pairs spanning the major clinical
# conjugation chemistries against protease-cleavable self-immolative triggers.
DEFAULT_CAMPAIGN: list[dict[str, str]] = [
    {"label": "Maleimide-ValCit", "handle": "Maleimide", "trigger": "Val-Cit-PAB"},
    {"label": "DBCO-ValCit", "handle": "DBCO", "trigger": "Val-Cit-PAB"},
    {"label": "Disulfide-ValCit", "handle": "Disulfide", "trigger": "Val-Cit-PAB"},
    {"label": "Maleimide-ValAla", "handle": "Maleimide", "trigger": "Val-Ala-PAB"},
]


def warhead_pair_smiles(handle: str, trigger: str) -> str:
    """Return the LinkInvent ``w1(*)|w2(*)`` string for a handle/trigger label."""
    return f"{CONJUGATION_HANDLES[handle]['smiles']}|{CLEAVABLE_TRIGGERS[trigger]['smiles']}"


def _trigger_matcher(trigger_smiles: str):
    """Return an RDKit query mol for the trigger fragment (attachment point removed).

    Used to keep only *assembled ADC linkers* (warhead--linker--trigger) and drop
    generic seed/fallback molecules that can leak into the candidate list.
    """
    try:
        from rdkit import Chem

        core = trigger_smiles.replace("*", "").replace("()", "")
        q = Chem.MolFromSmiles(core)
        if q is None:
            q = Chem.MolFromSmarts("c1ccc(CO)cc1")  # PABC self-immolative benzyl alcohol
        return q
    except Exception:
        return None


def _is_assembled_linker(smiles: str, query) -> bool:
    if query is None:
        return True
    try:
        from rdkit import Chem

        m = Chem.MolFromSmiles(smiles)
        return m is not None and m.HasSubstructMatch(query)
    except Exception:
        return True


def _serialise_candidates(state, limit: int, trigger_smiles: str | None = None) -> list[dict[str, Any]]:
    query = _trigger_matcher(trigger_smiles) if trigger_smiles else None
    scored = [
        m
        for m in state.candidate_molecules
        if m.score is not None and _is_assembled_linker(m.smiles, query)
    ]
    scored.sort(key=lambda m: m.score, reverse=True)
    out: list[dict[str, Any]] = []
    for mol in scored[:limit]:
        out.append(
            {
                "name": mol.name,
                "smiles": mol.smiles,
                "score": mol.score,
                "descriptors": mol.descriptors,
            }
        )
    return out


def run_campaign(
    request: str,
    campaign: list[dict[str, str]] | None = None,
    *,
    run_mode: str | RunMode = RunMode.CHEAP,
    run_root: str | Path = "runs",
    device: str = "cpu",
    reinvent_steps: int = 60,
    reinvent_batch: int = 64,
    max_iterations: int = 3,
    run_reinvent: bool = True,
    top_per_pair: int = 8,
    config_dir: str | Path = "configs",
) -> dict[str, Any]:
    """Run the autonomous ADC-linker loop once per warhead pair and aggregate.

    Returns a JSON-serialisable campaign record (per-pair results + a pooled,
    globally-ranked candidate list) and writes it to
    ``<run_root>/campaign_<timestamp>/campaign.json``.
    """

    campaign = campaign or DEFAULT_CAMPAIGN
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    campaign_dir = Path(run_root) / f"campaign_{timestamp}"
    campaign_dir.mkdir(parents=True, exist_ok=True)

    pair_records: list[dict[str, Any]] = []
    pooled: list[dict[str, Any]] = []

    for spec in campaign:
        handle, trigger, label = spec["handle"], spec["trigger"], spec["label"]
        wp = warhead_pair_smiles(handle, trigger)
        logger.info("campaign pair %s: %s", label, wp)

        profile = ADCGoalProfile()
        strategy = ADCStrategy(
            run_type="sampling",
            device=device,
            run=run_reinvent,
            max_steps=reinvent_steps,
            batch_size=reinvent_batch,
            min_steps=min(25, reinvent_steps),
        )
        state = run_demo(
            request,
            run_mode=run_mode,
            config_dir=config_dir,
            run_root=run_root,
            max_iterations=max_iterations,
            initial_metadata={
                "adc_goal_profile": profile.model_dump(mode="json"),
                "adc_strategy": strategy.model_dump(mode="json"),
                "adc_strategy_caps": {"max_steps": reinvent_steps, "batch_size": reinvent_batch},
                "adc_warhead_pair": wp,
            },
        )

        candidates = _serialise_candidates(
            state, top_per_pair, trigger_smiles=CLEAVABLE_TRIGGERS[trigger]["smiles"]
        )
        reinvent_meta = state.metadata.get("reinvent", {})
        record = {
            "label": label,
            "handle": handle,
            "handle_chemistry": CONJUGATION_HANDLES[handle]["chemistry"],
            "trigger": trigger,
            "trigger_mechanism": CLEAVABLE_TRIGGERS[trigger]["trigger"],
            "warhead_pair": wp,
            "run_dir": state.run_dir,
            "iterations": state.iteration,
            "final_run_type": reinvent_meta.get("run_type"),
            "reinvent_mock": bool(
                (state.metadata.get("reinvent_result") or {}).get("mock", False)
            ),
            "goal_profile": state.metadata.get("adc_goal_profile"),
            "decision_trail": state.metadata.get("adc_decision_trail", []),
            "top_candidates": candidates,
        }
        pair_records.append(record)

        for c in candidates:
            if c.get("score") is None:
                continue
            pooled.append({**c, "pair_label": label, "handle": handle, "trigger": trigger})

    pooled.sort(key=lambda c: c["score"], reverse=True)

    result = {
        "request": request,
        "timestamp": timestamp,
        "campaign_dir": str(campaign_dir),
        "n_pairs": len(pair_records),
        "pairs": pair_records,
        "pooled_ranked": pooled,
    }
    (campaign_dir / "campaign.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info("campaign complete: %s", campaign_dir / "campaign.json")
    return result
