from __future__ import annotations

from hackathon_agents.schemas.tasks import DiscoveryPlan, DiscoveryPlanStep
from hackathon_agents.state import DiscoveryStatePayload


def run(state: DiscoveryStatePayload) -> DiscoveryStatePayload:
    state.plan = DiscoveryPlan(
        objective=state.original_user_request,
        assumptions=[
            "Use deterministic tools first, then summarize uncertainty.",
            "Prefer local models for bulk ideation and hosted models for final checks when allowed.",
        ],
        steps=[
            DiscoveryPlanStep(
                name="Generate initial candidates",
                description="Seed plausible substrate candidates and keep provenance explicit.",
                agent="chemist",
            ),
            DiscoveryPlanStep(
                name="Run deterministic tools",
                description="Validate SMILES, compute descriptors, and create simple plots.",
                agent="tool_executor",
                tool_names=["rdkit", "plotting"],
            ),
            DiscoveryPlanStep(
                name="Optional DFT wrappers",
                description="Check xTB and ORCA availability and run only when configured and installed.",
                agent="dft",
                tool_names=["xtb", "orca"],
            ),
            DiscoveryPlanStep(
                name="Rank and write report",
                description="Critique candidates and produce a DOCX report plus serialized state.",
                agent="critic",
                tool_names=["doc_writer"],
            ),
        ],
    )
    _set_default_saturn_oracle(state)
    state.append_message("planner: created deterministic discovery plan")
    return state


def _set_default_saturn_oracle(state: DiscoveryStatePayload) -> None:
    """Seed a deterministic default Saturn oracle if none was provided.

    This makes Saturn generation config-gated like the other tools (xTB, ORCA):
    the planner proposes a sensible, drug-like oracle and RL setting without any
    human input. The graph's chemist node still decides whether Saturn is
    actually enabled via ``config.tool_enabled("saturn")``; if disabled, the
    chemist falls back to its deterministic seed molecules.

    The default oracle balances drug-likeness (``qed``) with synthetic
    accessibility (``sa``) using a product aggregator, which is a conservative,
    defensible starting point for de novo design.
    """

    if "saturn" in state.metadata:
        return
    state.metadata["saturn"] = {
        "objective": state.original_user_request,
        "oracle": [
            {"name": "qed", "weight": 1.0},
            {"name": "sa", "weight": 0.5},
        ],
        "aggregator": "product",
        "n_steps": 50,
        "batch_size": 64,
        "use_diversity_filter": True,
        # run=False keeps the demo offline-safe; the Saturn tool falls back to a
        # deterministic mock when the real framework is not installed.
        "run": False,
    }
    state.metadata["saturn_source"] = "planner_default"
