from __future__ import annotations

from hackathon_agents.agents.model_helpers import call_agent_model
from hackathon_agents.config import AppConfig
from hackathon_agents.schemas.tasks import DiscoveryPlan, DiscoveryPlanStep
from hackathon_agents.state import DiscoveryStatePayload


def run(state: DiscoveryStatePayload, config: AppConfig | None = None) -> DiscoveryStatePayload:
    model_plan = call_agent_model(
        state=state,
        config=config,
        agent_name="planner",
        task_type="planner",
        response_model=DiscoveryPlan,
        expected_difficulty="medium",
        user_payload={
            "objective": state.original_user_request,
            "run_mode": state.run_mode.value,
            "max_iterations": state.max_iterations,
            "available_tools": sorted(config.tools) if config else [],
            "instructions": [
                "Create a bounded scientific discovery plan.",
                "Prefer deterministic tools before model-only reasoning.",
                "Use only tool names that exist in available_tools.",
            ],
        },
    )
    if model_plan is not None:
        state.plan = model_plan
        state.append_message("planner: created model-backed discovery plan")
        return state

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
