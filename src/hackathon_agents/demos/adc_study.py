"""Finalize the ADC design study: Boltz structural yardstick + benchmark + paper.

Given a completed grid sweep (``adc_grid.run_grid`` -> grid.json), this:
  1. selects the best designed linker from each protease-cleavable context,
  2. co-folds those + commercial controls against cathepsin B with Boltz-2 (SSH),
  3. attaches independent yardsticks + novelty via ``linker_benchmark``,
  4. writes benchmark.json + boltz.json and builds the study paper (main + supp).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from hackathon_agents.logging_config import configure_logging, get_logger
from hackathon_agents.tools.adc_analysis import grid_stats
from hackathon_agents.tools.adc_study_paper import build_study_paper
from hackathon_agents.tools.boltz_tools import BoltzJobInput, run_boltz_2
from hackathon_agents.tools.linker_benchmark import COMMERCIAL_LINKERS, benchmark_designed

logger = get_logger(__name__)

# Human cathepsin B mature enzyme (UniProt P07858) — the protease that cleaves
# Val-Cit / Val-Ala PABC linkers.
CATHEPSIN_B = (
    "LPASFDAREQWPQCPTIKEIRDQGSCGSCWAFGAVEAISDRICIHTNAHVSVEVSAEDLLTCCGSMCGDGCNGGYPAEAWNFWTRKGLVSGG"
    "LYESHVGCRPYSIPPCEHHVNGSRPPCTGEGDTPKCSKICEPGYSPTYKQDKHYGYNSYSVSNSEKDIMAEIYKNGPVEGAFSVYSDFLLYK"
    "SGVYQHVTGEMMGGHAIRILGWGVENGTPYWLVANSWNTDWGDNGFFKILRGQDHCGIESEVVAGIPRTDQYWEKI"
)

# Commercial controls for the co-fold panel (positive: protease substrate; negative: bare spacer).
_BOLTZ_CONTROLS = ["mc-Val-Cit-PABC", "mc-Val-Ala-PABC", "maleimidocaproyl (mc)", "AcBut hydrazone"]


def _boltz_one(label: str, kind: str, smiles: str, work_root: Path, *, recycling: int, sampling: int) -> dict[str, Any]:
    job = BoltzJobInput(
        id=label.replace("/", "_").replace(" ", "_")[:40],
        work_dir=str(work_root / label.replace("/", "_").replace(" ", "_")[:40]),
        target_protein_sequence=CATHEPSIN_B,
        ligand_smiles=smiles,
        run_mode="ssh_remote", device="cuda", run=True, single_sequence=True,
        recycling_steps=recycling, diffusion_steps=sampling, timeout_seconds=1800,
        ssh_host=os.environ["REINVENT_SSH_HOST"], ssh_port=int(os.environ.get("REINVENT_SSH_PORT", "22")),
        ssh_user=os.environ.get("REINVENT_SSH_USER", "root"),
        ssh_key_path=os.path.expanduser(os.environ.get("REINVENT_SSH_KEY", "~/.ssh/id_pods")),
    )
    res = run_boltz_2(job)
    d = res.data if res.ok else {}
    return {
        "label": label, "kind": kind, "smiles": smiles,
        "ok": res.ok, "status": d.get("status"),
        "iptm": d.get("iptm"), "plddt": d.get("plddt"),
        "binding_affinity_kd_nm": d.get("binding_affinity_kd_nm"),
        "binding_energy_kcal_mol": d.get("binding_energy_kcal_mol"),
        "error": None if res.ok else res.error,
    }


def run_boltz_panel(stats: dict[str, Any], work_root: Path, *, max_designed: int = 6, recycling: int = 1, sampling: int = 25) -> list[dict[str, Any]]:
    """Co-fold best designed linkers (protease contexts) + commercial controls vs cathepsin B."""
    work_root.mkdir(parents=True, exist_ok=True)
    panel: list[tuple[str, str, str]] = []  # (label, kind, smiles)

    # Best designed linker from each protease-cleavable context (cathepsin B should
    # recognise these).
    by_ctx: dict[str, dict[str, Any]] = {}
    for c in stats["pooled"]:
        if "Cit" not in c.get("trigger", "") and "Ala" not in c.get("trigger", ""):
            continue
        key = f"{c['handle']}/{c['trigger']}"
        if key not in by_ctx or (c.get("score") or 0) > (by_ctx[key].get("score") or 0):
            by_ctx[key] = c
    for key, c in sorted(by_ctx.items(), key=lambda kv: -(kv[1].get("score") or 0))[:max_designed]:
        panel.append((key, "designed", c["smiles"]))

    # Payload-aware negative control: the oligonucleotide-optimal rigid non-cleavable
    # design. Cathepsin B should NOT recognise it (low interface ipTM) -- the
    # structural counterpart of the payload-class ranking flip.
    neg = None
    for c in stats["pooled"]:
        if "rigid" in c.get("trigger", "").lower() or "Non-cleavable-rigid" == c.get("trigger"):
            if neg is None or (c.get("score") or 0) > (neg.get("score") or 0):
                neg = c
    if neg is not None:
        panel.append((f"{neg['handle']}/Non-cleavable-rigid", "negative", neg["smiles"]))

    comm = {x["name"]: x for x in COMMERCIAL_LINKERS}
    for name in _BOLTZ_CONTROLS:
        if name in comm:
            panel.append((name, "commercial", comm[name]["smiles"]))

    logger.info("boltz panel: %d co-folds", len(panel))
    results = []
    for label, kind, smiles in panel:
        rec = _boltz_one(label, kind, smiles, work_root, recycling=recycling, sampling=sampling)
        logger.info("boltz %s (%s): ok=%s ipTM=%s Kd=%s", label, kind, rec["ok"], rec.get("iptm"), rec.get("binding_affinity_kd_nm"))
        results.append(rec)
    return results


def finalize_study(grid_path: str | Path, *, run_boltz: bool = True, out_dir: str | Path | None = None) -> dict[str, Any]:
    configure_logging()
    grid_path = Path(grid_path)
    grid = json.loads(grid_path.read_text(encoding="utf-8"))
    grid_dir = Path(grid.get("grid_dir", grid_path.parent))
    out_dir = Path(out_dir) if out_dir else grid_dir / "study"
    out_dir.mkdir(parents=True, exist_ok=True)

    stats = grid_stats(grid)
    logger.info("grid stats: %d contexts, %d designed, %d real runs", len(stats["contexts"]), len(stats["pooled"]), stats["n_real"])

    # Benchmark: independent yardsticks + novelty on the pooled designed linkers.
    benchmark = benchmark_designed(stats["pooled"][:40])
    benchmark_path = out_dir / "benchmark.json"
    benchmark_path.write_text(json.dumps(benchmark, indent=2), encoding="utf-8")

    boltz_path = None
    if run_boltz:
        boltz = run_boltz_panel(stats, out_dir / "boltz_jobs")
        boltz_path = out_dir / "boltz.json"
        boltz_path.write_text(json.dumps(boltz, indent=2), encoding="utf-8")

    paper = build_study_paper(grid_path, benchmark_path, boltz_path, out_dir / "paper")
    return {"out_dir": str(out_dir), "benchmark": str(benchmark_path),
            "boltz": str(boltz_path) if boltz_path else None,
            "paper_ok": paper.ok, "paper": paper.data if paper.ok else paper.error}
