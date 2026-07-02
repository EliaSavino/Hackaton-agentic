"""Study 2 (revised): payload-class-aware controlled design sweep.

Two blocks, unioned and deduped into a single resumable grid:

* **Block 1 - conjugation-chemistry sweep** (payload = cytotoxin). All eight
  conjugation handles (now including the tetrazine/TCO IEDDA pair) across three
  triggers spanning protease, glycosidase and non-cleavable release. Answers:
  do the new IEDDA handles hold up, and does the conjugation ranking survive?

* **Block 2 - payload-class sweep** (the headline). Two representative handles
  across a common trigger panel {protease-cleavable, non-cleavable-rigid,
  non-cleavable-flexible} under all three payload classes. Because the *same*
  contexts are scored under different payload profiles, the ranking flips:
  cleavable wins for cytotoxins, the rigid non-cleavable (sulfo-SMCC) cap wins
  for oligonucleotides, and cleavable-but-plasma-stable wins for immunomodulators.

The scorer dimensions are held fixed; only the payload profile, warhead context
and seed vary, so this is still a controlled experiment with payload as the top
lever. See ``PLAN_STUDY2.md`` for the rationale.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hackathon_agents.demos.adc_grid import run_grid
from hackathon_agents.logging_config import get_logger
from hackathon_agents.tools.payload_profiles import PAYLOAD_CLASSES, derive_payload_rules

logger = get_logger(__name__)

# Block 1 — conjugation-chemistry sweep (extends Study 2 with IEDDA), cytotoxin.
BLOCK1_HANDLES = ["Maleimide", "Bromoacetamide", "DBCO", "Disulfide", "NHS_ester", "Oxyamine", "Tetrazine", "TCO"]
BLOCK1_TRIGGERS = ["Val-Cit-PABC", "Glucuronide", "Non-cleavable"]

# Block 2 — payload-class sweep (the headline).
BLOCK2_HANDLES = ["Maleimide", "DBCO"]
BLOCK2_TRIGGERS = ["Val-Cit-PABC", "Non-cleavable-rigid", "Non-cleavable"]
BLOCK2_PAYLOADS = ["cytotoxin", "oligonucleotide", "immunomodulator"]


def build_study2_cells() -> list[dict[str, str]]:
    """Curated, deduped union of Block 1 and Block 2 cells."""
    seen: set[tuple[str, str, str]] = set()
    cells: list[dict[str, str]] = []

    def add(handle: str, trigger: str, payload: str) -> None:
        key = (handle, trigger, payload)
        if key in seen:
            return
        seen.add(key)
        cells.append({"handle": handle, "trigger": trigger, "payload": payload})

    for h in BLOCK1_HANDLES:
        for t in BLOCK1_TRIGGERS:
            add(h, t, "cytotoxin")
    for h in BLOCK2_HANDLES:
        for t in BLOCK2_TRIGGERS:
            for p in BLOCK2_PAYLOADS:
                add(h, t, p)
    return cells


def payload_rule_card() -> list[dict[str, Any]]:
    """The agentic literature step's output for each payload class (for the paper)."""
    return [derive_payload_rules(p) for p in PAYLOAD_CLASSES]


def run_study2_grid(
    *,
    seeds: tuple[int, ...] = (0, 1),
    steps: int = 40,
    batch: int = 32,
    max_workers: int = 5,
    resume_dir: str | Path | None = "runs/grid_war3",
) -> dict[str, Any]:
    """Run the revised payload-aware grid on the pod (shared-pod-safe defaults)."""
    cells = build_study2_cells()
    logger.info("study2 grid: %d curated cells x %d seeds", len(cells), len(seeds))
    for card in payload_rule_card():
        logger.info("payload rule [%s] cleavage=%s rigidity=%s stability=%s (%s)",
                    card["payload"], card["cleavage_preference"], card["rigidity"],
                    card["stability_priority"], card["mode"])
    return run_grid(
        cells=cells,
        seeds=seeds,
        steps=steps,
        batch=batch,
        max_workers=max_workers,
        resume_dir=resume_dir,
    )
