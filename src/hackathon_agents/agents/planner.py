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
    state.append_message("planner: created deterministic discovery plan")
    return state
