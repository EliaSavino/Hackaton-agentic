from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from hackathon_agents.config import RunMode, load_config
from hackathon_agents.graph import build_graph
from hackathon_agents.logging_config import configure_logging, get_logger
from hackathon_agents.state import DiscoveryStatePayload

logger = get_logger(__name__)


def run_demo(
    request: str,
    run_mode: str | RunMode | None = None,
    config_dir: str | Path = "configs",
    run_root: str | Path = "runs",
    max_iterations: int = 3,
    min_valid_candidates: int = 10,
    score_threshold: float = 0.75,
) -> DiscoveryStatePayload:
    configure_logging()
    config = load_config(config_dir=config_dir, run_mode=run_mode)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(run_root) / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    logger.info("starting discovery demo in %s", run_dir)
    state = DiscoveryStatePayload(
        original_user_request=request,
        run_dir=str(run_dir),
        run_mode=config.run_mode,
        max_iterations=max_iterations,
        metadata={
            "min_valid_candidates": min_valid_candidates,
            "score_threshold": score_threshold,
        },
    )
    graph = build_graph(config)
    final_state = graph.invoke(state)

    state_path = run_dir / "state.json"
    state_path.write_text(final_state.model_dump_json(indent=2), encoding="utf-8")
    final_state.append_message(f"demo: wrote state to {state_path}")
    state_path.write_text(final_state.model_dump_json(indent=2), encoding="utf-8")
    return final_state
