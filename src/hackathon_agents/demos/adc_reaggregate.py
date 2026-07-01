"""Rebuild a clean campaign record from per-run state.json files.

The live campaign truncates each pair's candidate list to the top-N *before*
filtering, and the chemist can leak a few generic seed molecules into the
candidate pool. This re-aggregation re-reads the full candidate list from every
pair's ``state.json``, keeps only genuine assembled linkers (warhead--linker--
trigger, matched by the trigger substructure), re-ranks, and writes a clean
``campaign_clean.json`` for the paper writer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hackathon_agents.demos.adc_campaign import (
    CLEAVABLE_TRIGGERS,
    _is_assembled_linker,
    _trigger_matcher,
)


def reaggregate(campaign_json: str | Path, top_per_pair: int = 8) -> dict[str, Any]:
    campaign = json.loads(Path(campaign_json).read_text(encoding="utf-8"))
    pooled: list[dict[str, Any]] = []
    for pair in campaign.get("pairs", []):
        trigger = pair.get("trigger")
        trig_smiles = CLEAVABLE_TRIGGERS.get(trigger, {}).get("smiles")
        query = _trigger_matcher(trig_smiles) if trig_smiles else None
        state_path = Path(pair["run_dir"]) / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        cands = [
            {
                "name": m.get("name"),
                "smiles": m.get("smiles"),
                "score": m.get("score"),
                "descriptors": m.get("descriptors", {}),
            }
            for m in state.get("candidate_molecules", [])
            if m.get("score") is not None and _is_assembled_linker(m.get("smiles", ""), query)
        ]
        cands.sort(key=lambda c: c["score"], reverse=True)
        pair["n_assembled_linkers"] = len(cands)
        pair["top_candidates"] = cands[:top_per_pair]
        for c in cands[:top_per_pair]:
            pooled.append({**c, "pair_label": pair["label"], "handle": pair["handle"], "trigger": trigger})
    pooled.sort(key=lambda c: c["score"], reverse=True)
    campaign["pooled_ranked"] = pooled
    out = Path(campaign["campaign_dir"]) / "campaign_clean.json"
    out.write_text(json.dumps(campaign, indent=2), encoding="utf-8")
    return campaign
