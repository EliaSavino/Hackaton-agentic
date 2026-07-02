"""Controlled design-grid sweep: conjugation chemistry x cleavable trigger.

Holds the ADC scoring objective FIXED and varies only (a) the warhead context and
(b) the RNG seed, so any difference between grid cells is attributable to the
warhead chemistry rather than objective drift. Each cell is a REINVENT LinkInvent
*staged-learning* run (RL) on the pod over SSH — NOT the full LLM agent loop — which
makes the sweep a clean controlled experiment and cheaply parallelisable.

The grid axes are the two design levers named in the problem statement: robust
conjugation chemistries x tunable cleavage triggers. Handles are chosen by
frequency in the distilled Library A, filtered to groups that are a chemically
valid *standalone* antibody-conjugation warhead and that span the distinct
conjugation biologies. Triggers span the clinically-precedented release
mechanisms. See PLAN.md section 1 for the full selection rationale.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from hackathon_agents.logging_config import get_logger
from hackathon_agents.schemas.linkers import ADCGoalProfile
from hackathon_agents.tools.adc_linker_objective import build_adc_linkinvent_objective, score_adc_linker
from hackathon_agents.tools.reinvent_tools import ReinventInput, generate_with_reinvent

logger = get_logger(__name__)


# Conjugation handles: one LinkInvent attachment point (*) where the designed
# spacer begins. lib_a_count = frequency in the distilled Library A.
GRID_HANDLES: dict[str, dict[str, Any]] = {
    "Maleimide": {"smiles": "O=C1C=CC(=O)N1*", "chemistry": "cysteine thiol-Michael addition", "lib_a_count": 83},
    "Bromoacetamide": {"smiles": "*NC(=O)CBr", "chemistry": "cysteine alkylation (irreversible, retro-Michael-free)", "lib_a_count": 3},
    "DBCO": {"smiles": "*N1Cc2ccccc2C#Cc2ccccc21", "chemistry": "copper-free strain-promoted click (SPAAC)", "lib_a_count": 131},
    "Disulfide": {"smiles": "*SSc1ccccn1", "chemistry": "pyridyl-disulfide exchange (redox-labile conjugation)", "lib_a_count": 6},
    "NHS_ester": {"smiles": "*C(=O)ON1C(=O)CCC1=O", "chemistry": "lysine amide coupling", "lib_a_count": 7},
    "Oxyamine": {"smiles": "*CON", "chemistry": "aldehyde-tag / HIPS oxime ligation", "lib_a_count": 79},
}

# Cleavable triggers: attachment point at the linker-facing terminus. The
# self-immolative benzylic alcohol (PAB) or glycosidic aryl is left toward the
# payload. ``require_cleavable`` False = a non-cleavable control (payload release
# by antibody catabolism), scored with the cleavable-motif requirement relaxed.
GRID_TRIGGERS: dict[str, dict[str, Any]] = {
    "Val-Cit-PABC": {
        "smiles": "CC(C)[C@@H](C(=O)N[C@@H](CCCNC(=O)N)C(=O)Nc1ccc(CO)cc1)N*",
        "mechanism": "lysosomal cathepsin-B protease (self-immolative PABC)",
        "require_cleavable": True,
    },
    "Val-Ala-PABC": {
        "smiles": "CC(C)[C@@H](C(=O)N[C@@H](C)C(=O)Nc1ccc(CO)cc1)N*",
        "mechanism": "lysosomal cathepsin-B protease (Val-Ala, higher plasma stability)",
        "require_cleavable": True,
    },
    "Glucuronide": {
        "smiles": "*NC(=O)[C@@H]1O[C@@H](Oc2ccc(CO)cc2)[C@@H](O)[C@H](O)[C@H]1O",
        "mechanism": "beta-glucuronidase glycosidic cleavage (hydrophilic trigger)",
        "require_cleavable": True,
        # The sugar's anomeric acetal trips the plasma-labile acetal alert, a false
        # positive: glycosides are enzymatically (not spontaneously) cleaved. Relax
        # the hard stability filter for this context so the sugar isn't penalised.
        "enforce_stability": False,
    },
    "Non-cleavable": {
        "smiles": "*NCc1ccccc1",
        "mechanism": "non-cleavable (payload release by antibody catabolism)",
        "require_cleavable": False,
    },
}

DEFAULT_HANDLE_ORDER = ["Maleimide", "Bromoacetamide", "DBCO", "Disulfide", "NHS_ester", "Oxyamine"]
DEFAULT_TRIGGER_ORDER = ["Val-Cit-PABC", "Val-Ala-PABC", "Glucuronide", "Non-cleavable"]


def build_grid(handles: list[str] | None = None, triggers: list[str] | None = None) -> list[dict[str, str]]:
    handles = handles or DEFAULT_HANDLE_ORDER
    triggers = triggers or DEFAULT_TRIGGER_ORDER
    return [{"handle": h, "trigger": t} for h in handles for t in triggers]


def warhead_pair(handle: str, trigger: str) -> str:
    return f"{GRID_HANDLES[handle]['smiles']}|{GRID_TRIGGERS[trigger]['smiles']}"


def validate_warheads() -> list[str]:
    """Return a list of problems; empty means every warhead is a valid single-* fragment."""
    from rdkit import Chem

    problems: list[str] = []
    for name, spec in {**GRID_HANDLES, **GRID_TRIGGERS}.items():
        mol = Chem.MolFromSmiles(spec["smiles"])
        if mol is None:
            problems.append(f"{name}: unparseable ({spec['smiles']})")
            continue
        dummies = [a for a in mol.GetAtoms() if a.GetAtomicNum() == 0]
        if len(dummies) != 1:
            problems.append(f"{name}: {len(dummies)} attachment points (need 1)")
        elif dummies[0].GetDegree() != 1:
            problems.append(f"{name}: attachment point degree {dummies[0].GetDegree()}")
    return problems


def _profile_for(trigger: str) -> ADCGoalProfile:
    profile = ADCGoalProfile()
    meta = GRID_TRIGGERS[trigger]
    if not meta["require_cleavable"]:
        # Non-cleavable control: don't require/reward a cleavable motif.
        profile.require_cleavable_motif = False
        profile.weights["cleavability"] = 0.0
    if meta.get("enforce_stability", True) is False:
        # Relax the acetal/hydrazone hard filter where it is a known false positive
        # (e.g. glycosidic sugars). The alert still informs the reported subscore.
        profile.enforce_stability_alerts = False
    return profile


def _ssh_env() -> dict[str, Any]:
    return {
        "run_mode": "ssh_remote",
        "ssh_host": os.environ["REINVENT_SSH_HOST"],
        "ssh_port": int(os.environ.get("REINVENT_SSH_PORT", "22")),
        "ssh_user": os.environ.get("REINVENT_SSH_USER", "root"),
        "ssh_key_path": os.path.expanduser(os.environ.get("REINVENT_SSH_KEY", "~/.ssh/id_pods")),
        "remote_workdir": os.environ.get("REINVENT_REMOTE_WORKDIR", "/reinvent_runs"),
        "remote_reinvent_executable": os.environ.get("REINVENT_REMOTE_EXECUTABLE", "reinvent"),
        "remote_prior_base": os.environ.get("REINVENT_REMOTE_PRIOR_BASE", "/reinvent_priors"),
    }


def _run_one(cell: dict[str, str], seed: int, *, work_root: Path, steps: int, batch: int, top_n: int) -> dict[str, Any]:
    handle, trigger = cell["handle"], cell["trigger"]
    wp = warhead_pair(handle, trigger)
    profile = _profile_for(trigger)
    obj = build_adc_linkinvent_objective(
        profile,
        warhead_pair=wp,
        run_type="staged_learning",
        run=True,
        device="cpu",
        max_steps=steps,
        min_steps=min(25, steps),
        batch_size=batch,
    )
    label = f"{handle}__{trigger}__seed{seed}"
    obj["seed"] = seed
    obj["work_dir"] = str(work_root / label)
    obj["timeout_seconds"] = 1800  # generous ceiling: cleavable scoring is slow under contention
    obj.update(_ssh_env())
    inp = ReinventInput(**obj)

    result = generate_with_reinvent(inp)
    molecules = result.data.get("molecules", []) if result.ok else []
    mock = bool(result.data.get("mock")) if result.ok else True

    from rdkit import Chem

    trig_core = GRID_TRIGGERS[trigger]["smiles"].replace("*", "")
    query = Chem.MolFromSmiles(trig_core) or Chem.MolFromSmarts("c1ccccc1")

    scored: list[dict[str, Any]] = []
    for mol in molecules:
        smiles = mol.get("smiles")
        if not smiles:
            continue
        m = Chem.MolFromSmiles(smiles)
        if m is None or not m.HasSubstructMatch(query):
            continue  # keep only genuine assembled linkers
        composite, subscores = score_adc_linker(smiles, profile)
        if composite is None:
            continue
        scored.append(
            {
                "smiles": smiles,
                "score": composite,
                "subscores": subscores,
                "descriptors": mol.get("descriptors", {}),
            }
        )
    scored.sort(key=lambda c: c["score"], reverse=True)
    return {
        "handle": handle,
        "trigger": trigger,
        "seed": seed,
        "warhead_pair": wp,
        "mock": mock,
        "ok": result.ok,
        "error": None if result.ok else result.error,
        "n_assembled": len(scored),
        "best_score": scored[0]["score"] if scored else None,
        "top": scored[:top_n],
    }


def _job_key(handle: str, trigger: str, seed: int) -> str:
    return f"{handle}__{trigger}__seed{seed}"


def _load_done(records_path: Path) -> dict[str, dict[str, Any]]:
    """Read incrementally-persisted records; return {job_key: record} for finished jobs."""
    done: dict[str, dict[str, Any]] = {}
    if not records_path.exists():
        return done
    for line in records_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        # Only treat a real (non-mock, ok) result as done; retry failures on resume.
        if rec.get("ok") and not rec.get("mock"):
            done[_job_key(rec["handle"], rec["trigger"], rec["seed"])] = rec
    return done


def run_grid(
    *,
    seeds: tuple[int, ...] = (0, 1, 2),
    handles: list[str] | None = None,
    triggers: list[str] | None = None,
    steps: int = 60,
    batch: int = 64,
    max_workers: int = 8,
    top_n: int = 5,
    run_root: str | Path = "runs",
    resume_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run the grid x seeds sweep concurrently on the pod; resumable + incremental.

    Each completed job is appended to ``<grid_dir>/records.jsonl`` immediately, so a
    kill loses at most the in-flight jobs. Pass ``resume_dir`` to continue a prior
    sweep: already-finished (handle, trigger, seed) jobs are skipped.
    """
    import threading

    problems = validate_warheads()
    if problems:
        raise ValueError("Invalid warheads: " + "; ".join(problems))

    cells = build_grid(handles, triggers)
    if resume_dir is not None:
        grid_dir = Path(resume_dir)
        timestamp = grid_dir.name.replace("grid_", "")
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        grid_dir = Path(run_root) / f"grid_{timestamp}"
    work_root = grid_dir / "jobs"
    work_root.mkdir(parents=True, exist_ok=True)
    records_path = grid_dir / "records.jsonl"

    done = _load_done(records_path)
    jobs = [(cell, seed) for cell in cells for seed in seeds if _job_key(cell["handle"], cell["trigger"], seed) not in done]
    logger.info("grid sweep: %d cells x %d seeds; %d already done, %d to run, %d concurrent",
                len(cells), len(seeds), len(done), len(jobs), max_workers)

    records: list[dict[str, Any]] = list(done.values())
    write_lock = threading.Lock()
    with records_path.open("a", encoding="utf-8") as fh:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {
                ex.submit(_run_one, cell, seed, work_root=work_root, steps=steps, batch=batch, top_n=top_n): (cell, seed)
                for cell, seed in jobs
            }
            for fut in as_completed(futures):
                cell, seed = futures[fut]
                try:
                    rec = fut.result()
                except Exception as exc:  # pragma: no cover - defensive
                    rec = {"handle": cell["handle"], "trigger": cell["trigger"], "seed": seed, "ok": False, "error": f"{type(exc).__name__}: {exc}", "top": [], "n_assembled": 0, "best_score": None, "mock": True}
                records.append(rec)
                with write_lock:
                    fh.write(json.dumps(rec) + "\n")
                    fh.flush()
                logger.info("done %s__%s seed%s: ok=%s best=%s", cell["handle"], cell["trigger"], seed, rec.get("ok"), rec.get("best_score"))

    result = {
        "timestamp": timestamp,
        "grid_dir": str(grid_dir),
        "handles": handles or DEFAULT_HANDLE_ORDER,
        "triggers": triggers or DEFAULT_TRIGGER_ORDER,
        "seeds": list(seeds),
        "steps": steps,
        "batch": batch,
        "handle_meta": GRID_HANDLES,
        "trigger_meta": GRID_TRIGGERS,
        "records": records,
    }
    (grid_dir / "grid.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info("grid complete: %s", grid_dir / "grid.json")
    return result
