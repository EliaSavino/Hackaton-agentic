from __future__ import annotations

from hackathon_agents.agents.model_helpers import call_agent_model
from hackathon_agents.config import AppConfig
from hackathon_agents.schemas.tasks import DiscoveryPlan, DiscoveryPlanStep, PlannedTask, PlannerTaskGraph
from hackathon_agents.state import DiscoveryStatePayload
from hackathon_agents.tools.registry import build_tool_registry, summarize_tool_registry


def run(state: DiscoveryStatePayload, config: AppConfig | None = None) -> DiscoveryStatePayload:
    tool_registry = build_tool_registry(config) if config is not None else []
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
            "available_tools": [entry["name"] for entry in tool_registry if entry["enabled"]],
            "tool_registry_summary": summarize_tool_registry(tool_registry),
            "tool_registry": tool_registry,
            "instructions": [
                "Create a bounded scientific discovery plan.",
                "Prefer deterministic tools before model-only reasoning.",
                "Use only enabled tools from tool_registry unless explicitly explaining why a disabled tool is skipped.",
                "Respect execution_risk, mock_behavior, and external_side_effects when choosing tools.",
            ],
        },
    )
    if model_plan is not None:
        state.plan = model_plan
        _attach_planner_metadata(state, tool_registry)
        if not _set_default_adc_linker_objective(state):
            _set_default_saturn_oracle(state)
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
                description="Critique candidates and produce DOCX and LaTeX reports plus serialized state.",
                agent="critic",
                tool_names=["doc_writer", "latex_writer"],
            ),
            DiscoveryPlanStep(
                name="Record shared memory",
                description="Append compact progress notes for future users after each major workflow milestone.",
                agent="graph",
                tool_names=["memory_writer"],
            ),
        ],
    )
    _attach_planner_metadata(state, tool_registry)
    # ADC linker design is the primary challenge: prefer a REINVENT LinkInvent
    # objective. When it is active we skip the generic Saturn oracle to avoid two
    # generators competing on the same pass.
    if not _set_default_adc_linker_objective(state):
        _set_default_saturn_oracle(state)
    state.append_message("planner: created deterministic discovery plan")
    return state


def _attach_planner_metadata(state: DiscoveryStatePayload, tool_registry: list[dict] | None = None) -> None:
    if tool_registry is not None:
        state.metadata["tool_registry"] = tool_registry
        state.metadata["tool_registry_summary"] = summarize_tool_registry(tool_registry)
    state.metadata["planner_task_graph"] = _default_task_graph(state).model_dump(mode="json")


def _default_task_graph(state: DiscoveryStatePayload) -> PlannerTaskGraph:
    return PlannerTaskGraph(
        objective=state.original_user_request,
        tasks=[
            PlannedTask(
                id="plan",
                title="Plan bounded scientific workflow",
                task_type="planning",
                agent="planner",
                description="Create assumptions, task ordering, and tool choices.",
                expected_artifacts=["planner_task_graph"],
                status="completed" if state.plan else "planned",
            ),
            PlannedTask(
                id="generate_candidates",
                title="Generate candidate molecules",
                task_type="hypothesis_generation",
                agent="chemist",
                description="Create or refine candidate molecules with explicit provenance.",
                tool_names=["reinvent", "saturn"],
                depends_on=["plan"],
                expected_artifacts=["candidate_molecules"],
            ),
            PlannedTask(
                id="run_deterministic_tools",
                title="Run deterministic candidate tools",
                task_type="tool_execution",
                agent="tool_executor",
                description="Validate molecules, compute descriptors, filter candidates, and render plots.",
                tool_names=["rdkit", "plotting", "file_io"],
                depends_on=["generate_candidates"],
                expected_artifacts=["descriptors.csv", "qed_plot.png"],
            ),
            PlannedTask(
                id="critique",
                title="Critique and decide whether to iterate",
                task_type="criticism",
                agent="critic",
                description="Rank candidates, identify uncertainty, and request bounded follow-up if needed.",
                depends_on=["run_deterministic_tools"],
                expected_artifacts=["critic_decisions"],
            ),
            PlannedTask(
                id="write_reports",
                title="Write run reports",
                task_type="reporting",
                agent="writer",
                description="Write DOCX, LaTeX, publication paper, state, memory, and artifact index outputs.",
                tool_names=["doc_writer", "latex_writer", "paper_writer", "memory_writer"],
                depends_on=["critique"],
                expected_artifacts=["report.docx", "report.tex", "adc_paper.tex", "artifact_index.json"],
            ),
        ],
    )


_ADC_INTENT_KEYWORDS = (
    "adc",
    "antibody-drug",
    "antibody drug",
    "linker",
    "conjugate",
    "payload",
    "warhead",
    "cleavable",
    "maleimide",
)


def _set_default_adc_linker_objective(state: DiscoveryStatePayload) -> bool:
    """Seed a REINVENT LinkInvent objective when the task is ADC-linker design.

    Returns ``True`` when an ADC objective is active (already seeded, e.g. by the
    ``design-adc-linkers`` CLI command, or inferred from the request text), so
    the caller can skip the generic Saturn default. The chemist reads
    ``state.metadata["reinvent"]`` to run LinkInvent; the critic reads
    ``state.metadata["adc_goal_profile"]`` to score and steer.
    """

    from hackathon_agents.schemas.linkers import ADCGoalProfile
    from hackathon_agents.tools.adc_linker_objective import build_adc_linkinvent_objective

    already_active = "adc_goal_profile" in state.metadata or "reinvent" in state.metadata
    request = (state.original_user_request or "").lower()
    inferred = any(keyword in request for keyword in _ADC_INTENT_KEYWORDS)
    if not (already_active or inferred):
        return False

    profile = state.metadata.get("adc_goal_profile")
    if profile is None:
        profile = ADCGoalProfile()
        state.metadata["adc_goal_profile"] = profile.model_dump(mode="json")
    else:
        profile = ADCGoalProfile.model_validate(profile)

    if "reinvent" not in state.metadata:
        objective = build_adc_linkinvent_objective(profile, run=False)
        objective["objective"] = state.original_user_request
        state.metadata["reinvent"] = objective
        state.metadata["reinvent_source"] = "planner_adc_default"
    return True


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
