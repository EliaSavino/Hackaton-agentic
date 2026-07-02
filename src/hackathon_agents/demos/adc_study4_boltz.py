"""Study 4 Phase 7 — whole-CONJUGATE co-folding vs cathepsin B (CRITIQUE_S3 #9).

Study 3 co-folded the isolated linker fragment. Study 4 co-folds the assembled
handle-linker-PAYLOAD construct (the real payload attached), testing whether cathepsin B
still recognises the scissile linker when the bulky payload is present. The predicted
Kd should separate the cleavable cytotoxin/ISAC conjugates (recognised substrates) from
the rigid non-cleavable oligonucleotide conjugate (non-substrate) at the whole-conjugate
level — the structural counterpart of the payload-rule flip.

Small, pod-disciplined panel (few folds). Reuses the Study-3 Boltz SSH machinery.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import os

from hackathon_agents.logging_config import configure_logging, get_logger
from hackathon_agents.demos.adc_study import CATHEPSIN_B
from hackathon_agents.tools.boltz_tools import BoltzJobInput, run_boltz_2
from hackathon_agents.tools.real_payloads import PAYLOADS
from hackathon_agents.tools.linker_benchmark import COMMERCIAL_LINKERS

logger = get_logger(__name__)


def _boltz_conjugate(label: str, kind: str, linker_smiles: str, payload_smiles: str | None,
                     work_root: Path, *, recycling: int, sampling: int) -> dict[str, Any]:
    """Co-fold the WHOLE conjugate vs cathepsin B: linker = affinity binder (chain B),
    payload = co-folded cofactor (chain C). Each ligand is a valid single molecule, so
    boltz folds the full assembly (protein + linker + payload) rather than a dotted blob.
    Affinity is predicted on the scissile linker, which is what cathepsin B recognises.
    """
    job = BoltzJobInput(
        id=label.replace("/", "_").replace(" ", "_")[:40],
        work_dir=str(work_root / label.replace("/", "_").replace(" ", "_")[:40]),
        target_protein_sequence=CATHEPSIN_B,
        ligand_smiles=linker_smiles,
        cofactors=[payload_smiles] if payload_smiles else [],
        run_mode="ssh_remote", device="cuda", run=True, single_sequence=True,
        recycling_steps=recycling, diffusion_steps=sampling, timeout_seconds=1800,
        ssh_host=os.environ["REINVENT_SSH_HOST"], ssh_port=int(os.environ.get("REINVENT_SSH_PORT", "22")),
        ssh_user=os.environ.get("REINVENT_SSH_USER", "root"),
        ssh_key_path=os.path.expanduser(os.environ.get("REINVENT_SSH_KEY", "~/.ssh/id_pods")),
    )
    res = run_boltz_2(job)
    d = res.data if res.ok else {}
    return {
        "label": label, "kind": kind, "linker_smiles": linker_smiles,
        "payload_smiles": payload_smiles, "whole_conjugate": bool(payload_smiles),
        "ok": res.ok, "status": d.get("status"),
        "iptm": d.get("iptm"), "plddt": d.get("plddt"),
        "binding_affinity_kd_nm": d.get("binding_affinity_kd_nm"),
        "binding_energy_kcal_mol": d.get("binding_energy_kcal_mol"),
        "error": None if res.ok else res.error,
    }


def run_whole_conjugate_panel(
    shortlist_path: str | Path = "deliverables/study4/shortlist.json",
    out_path: str | Path = "deliverables/study4/boltz_whole_conjugate.json",
    *,
    per_class: int = 1,
    recycling: int = 1,
    sampling: int = 25,
) -> list[dict[str, Any]]:
    configure_logging()
    data = json.loads(Path(shortlist_path).read_text())
    shortlist = data["shortlist"]
    work_root = Path("deliverables/study4/boltz_jobs")
    work_root.mkdir(parents=True, exist_ok=True)

    panel: list[tuple[str, str, str, str | None]] = []  # (label, kind, linker, payload)
    for payload_class in ("cytotoxin", "immunomodulator", "oligonucleotide"):
        items = shortlist.get(payload_class, [])[:per_class]
        payload_smiles = (PAYLOADS.get(shortlist.get(payload_class, [{}])[0].get("real_payload", ""), {})
                          .get("smiles")) if items else None
        for i, it in enumerate(items):
            payload_smiles = PAYLOADS.get(it.get("real_payload", ""), {}).get("smiles")
            kind = "designed_conjugate" if payload_class != "oligonucleotide" else "negative_conjugate"
            label = f"{payload_class[:4]}-{it.get('handle','?')[:6]}-{i}"
            panel.append((label, kind, it["smiles"], payload_smiles))

    # Clinical control: the mc-Val-Cit-PABC substrate co-folded with MMAE payload.
    comm = {x["name"]: x for x in COMMERCIAL_LINKERS}
    if "mc-Val-Cit-PABC" in comm:
        panel.append(("clinical-mcValCitPABC+MMAE", "commercial_conjugate",
                      comm["mc-Val-Cit-PABC"]["smiles"], PAYLOADS.get("MMAE", {}).get("smiles")))

    logger.info("whole-conjugate boltz panel: %d co-folds", len(panel))
    results = []
    for label, kind, linker, payload in panel:
        rec = _boltz_conjugate(label, kind, linker, payload, work_root, recycling=recycling, sampling=sampling)
        logger.info("boltz %s (%s): ok=%s ipTM=%s Kd=%s", label, kind, rec["ok"],
                    rec.get("iptm"), rec.get("binding_affinity_kd_nm"))
        results.append(rec)

    Path(out_path).write_text(json.dumps(results, indent=2))
    logger.info("wrote %s", out_path)
    return results


if __name__ == "__main__":
    run_whole_conjugate_panel()
