"""Study 6 hypothesis test (Reviewer 2, Part VIII / criterion-1 novelty).

The agent, from the clinical antibody-oligonucleotide-conjugate literature (held-out, with
the rigid-non-cleavable siRNA paper withheld), derived a protease-cleavable Val-Cit rule for
ARCs. This turns that into a falsifiable, in-silico-tested prediction:

    Hypothesis: a protease-cleavable Val-Cit ARC linker is recognised (and thus releasable)
    by cathepsin B, unlike the rigid non-cleavable sulfo-SMCC standard.

We (1) build the ARC objective from the HELD-OUT-derived cleavable rule, (2) generate a
DBCO + Val-Cit-PABC ARC linker under it (REINVENT, real, on the pod), and (3) co-fold the
top design with the oligonucleotide payload against cathepsin B. If it is recognised (tight
Kd) while the rigid ARC design is not, the hypothesis has in-silico support.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from hackathon_agents.config import load_config
from hackathon_agents.logging_config import configure_logging, get_logger
from hackathon_agents.demos.adc_study5_generate import profile_from_rule, _generate_one, CLASS_WARHEAD
from hackathon_agents.demos.adc_study4_boltz import _boltz_conjugate
from hackathon_agents.tools.real_payloads import PAYLOADS

logger = get_logger(__name__)


def run_hypothesis(out_dir: str | Path = "deliverables/study6", src_dir: str | Path = "deliverables/study5",
                   *, steps: int = 40, batch: int = 32) -> dict[str, Any]:
    configure_logging()
    os.environ.setdefault("HACKATHON_AGENT_LLM_MODE", "always")
    load_config(env_file=".env")
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)

    # The cleavable ARC rule the agent derived from the clinical AOC literature (held-out).
    heldout = json.loads((Path(src_dir) / "heldout_predictions.json").read_text())
    arc_rule = heldout["oligonucleotide"]["full_chain"]["rule"]
    logger.info("held-out ARC rule: cleavage=%s rigidity=%s", arc_rule.get("cleavage_preference"), arc_rule.get("rigidity"))
    profile = profile_from_rule(arc_rule)  # cleavable

    # Generate a Val-Cit ARC linker (DBCO handle + Val-Cit-PABC trigger) under that objective.
    CLASS_WARHEAD["oligonucleotide_cleavable"] = ("DBCO", "Val-Cit-PABC")
    work_root = out / "reinvent_runs_hypothesis"; work_root.mkdir(parents=True, exist_ok=True)
    rec = _generate_one("oligonucleotide_cleavable", profile, steps=steps, batch=batch, work_root=work_root, top_n=6)
    logger.info("generated cleavable ARC: ok=%s mock=%s n_assembled=%s best=%s",
                rec["ok"], rec["mock"], rec["n_assembled"], rec["best_score"])

    top = rec["top"][0]["smiles"] if rec["top"] else None
    boltz_rec = None
    if top:
        oligo_payload = PAYLOADS.get("siRNA", {}).get("smiles")
        boltz_root = out / "boltz_jobs_hypothesis"; boltz_root.mkdir(parents=True, exist_ok=True)
        boltz_rec = _boltz_conjugate("arc-ValCit-hypothesis", "designed_conjugate", top, oligo_payload,
                                     boltz_root, recycling=1, sampling=25)
        logger.info("co-fold cleavable ARC: ok=%s ipTM=%s Kd=%s", boltz_rec["ok"], boltz_rec.get("iptm"),
                    boltz_rec.get("binding_affinity_kd_nm"))

    result = {
        "hypothesis": "A protease-cleavable Val-Cit ARC linker is recognised by cathepsin B, "
                      "unlike the rigid non-cleavable sulfo-SMCC standard.",
        "derived_from": "held-out ARC rule (clinical AOC literature, siRNA paper withheld)",
        "arc_rule": arc_rule,
        "generation": {k: rec[k] for k in ("ok", "mock", "n_assembled", "best_score", "warhead_pair", "top")},
        "cleavable_arc_design": top,
        "cofold": boltz_rec,
    }
    (out / "hypothesis_arc.json").write_text(json.dumps(result, indent=2))
    print("HYPOTHESIS_DONE design=", (top or "")[:50], "Kd=", (boltz_rec or {}).get("binding_affinity_kd_nm"))
    return result


if __name__ == "__main__":
    run_hypothesis()
