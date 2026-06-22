from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, TypedDict

from hackathon_agents.agents import chemist, critic, planner, writer
from hackathon_agents.config import AppConfig, RunMode
from hackathon_agents.logging_config import get_logger
from hackathon_agents.schemas.molecules import MoleculeFilterConstraints
from hackathon_agents.state import DiscoveryStatePayload
from hackathon_agents.tools.doc_writer import write_scientific_report
from hackathon_agents.tools.file_io import write_csv
from hackathon_agents.tools.latex_writer import write_latex_report
from hackathon_agents.tools.memory_writer import append_project_memory
from hackathon_agents.tools.orca import check_orca_availability, run_orca
from hackathon_agents.tools.plotting import generate_plot
from hackathon_agents.tools.rdkit_tools import compute_descriptors, filter_molecules, validate_smiles
from hackathon_agents.tools.xtb import check_xtb_availability

logger = get_logger(__name__)


class _GraphState(TypedDict, total=False):
    original_user_request: str
    plan: dict[str, Any] | None
    candidate_molecules: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    errors: list[str]
    critic_notes: list[str]
    critic_decisions: list[dict[str, Any]]
    final_report_path: str | None
    messages: list[str]
    run_dir: str | None
    run_mode: str
    iteration: int
    max_iterations: int
    needs_more_passes: bool
    stop_reason: str | None
    requested_next_actions: list[str]
    metadata: dict[str, Any]


class DiscoveryGraph:
    def __init__(self, config: AppConfig):
        self.config = config
        self._compiled = self._try_build_langgraph()

    def invoke(self, state: DiscoveryStatePayload | dict[str, Any]) -> DiscoveryStatePayload:
        payload = state if isinstance(state, DiscoveryStatePayload) else DiscoveryStatePayload.model_validate(state)
        self._write_memory(payload, "run_started", "Started a discovery agent run.", node="graph")
        if self._compiled is not None:
            result = self._compiled.invoke(payload.model_dump(mode="json"))
            return DiscoveryStatePayload.model_validate(result)
        return self._invoke_fallback(payload)

    def _invoke_fallback(self, state: DiscoveryStatePayload) -> DiscoveryStatePayload:
        state = self._planner_node(state)
        while True:
            state = self._chemist_node(state)
            state = self._tool_execution_node(state)
            state = self._critic_node(state)
            if self._route_after_critic_state(state) != "chemist":
                break
            state.append_message("graph: routing back to chemist for another bounded pass")
        state = self._writer_node(state)
        return state

    def _try_build_langgraph(self):
        try:
            from langgraph.graph import END, StateGraph
        except Exception:
            logger.debug("LangGraph is not installed; using deterministic fallback runner.")
            return None

        workflow = StateGraph(_GraphState)
        workflow.add_node("planner", self._dict_node(self._planner_node))
        workflow.add_node("chemist", self._dict_node(self._chemist_node))
        workflow.add_node("tool_execution", self._dict_node(self._tool_execution_node))
        workflow.add_node("critic", self._dict_node(self._critic_node))
        workflow.add_node("writer", self._dict_node(self._writer_node))
        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "chemist")
        workflow.add_edge("chemist", "tool_execution")
        workflow.add_edge("tool_execution", "critic")
        workflow.add_conditional_edges(
            "critic",
            self._route_after_critic,
            {
                "chemist": "chemist",
                "writer": "writer",
            },
        )
        workflow.add_edge("writer", END)
        return workflow.compile()

    def _dict_node(self, func: Callable[[DiscoveryStatePayload], DiscoveryStatePayload]):
        def wrapped(raw_state: dict[str, Any]) -> dict[str, Any]:
            state = DiscoveryStatePayload.model_validate(raw_state)
            return func(state).model_dump(mode="json")

        return wrapped

    def _planner_node(self, state: DiscoveryStatePayload) -> DiscoveryStatePayload:
        logger.info("planner node")
        state = planner.run(state, config=self.config)
        step_count = len(state.plan.steps) if state.plan else 0
        self._write_memory(state, "planner_completed", f"Created a discovery plan with {step_count} steps.", node="planner")
        return state

    def _chemist_node(self, state: DiscoveryStatePayload) -> DiscoveryStatePayload:
        logger.info("chemist node")
        state.iteration += 1
        state.append_message(f"graph: starting pass {state.iteration}/{state.max_iterations}")
        state = chemist.run(state, config=self.config)
        self._write_memory(
            state,
            "chemist_completed",
            f"Completed candidate-generation pass {state.iteration} with {len(state.candidate_molecules)} candidates.",
            node="chemist",
        )
        return state

    def _tool_execution_node(self, state: DiscoveryStatePayload) -> DiscoveryStatePayload:
        logger.info("tool execution node")
        run_dir = _ensure_run_dir(state)
        initial_tool_count = len(state.tool_results)

        descriptor_rows: list[dict[str, Any]] = []
        for molecule in state.candidate_molecules:
            if molecule.descriptors.get("qed") is not None:
                descriptor_rows.append(
                    {
                        "name": molecule.name or molecule.smiles,
                        "smiles": molecule.smiles,
                        "mol_wt": molecule.descriptors.get("mol_wt"),
                        "logp": molecule.descriptors.get("logp"),
                        "qed": molecule.descriptors.get("qed"),
                    }
                )
                continue

            validation = validate_smiles(molecule.smiles)
            state.add_tool_result("rdkit.validate_smiles", validation)
            if not validation.ok or not validation.data.get("valid"):
                continue

            descriptors = compute_descriptors(molecule.smiles)
            state.add_tool_result("rdkit.compute_descriptors", descriptors)
            if descriptors.ok:
                molecule.descriptors = descriptors.data
                descriptor_rows.append(
                    {
                        "name": molecule.name or molecule.smiles,
                        "smiles": molecule.smiles,
                        "mol_wt": descriptors.data.get("mol_wt"),
                        "logp": descriptors.data.get("logp"),
                        "qed": descriptors.data.get("qed"),
                    }
                )

        if descriptor_rows:
            csv_result = write_csv(run_dir / "descriptors.csv", descriptor_rows)
            state.add_tool_result("file_io.write_csv", csv_result)
            plot_result = generate_plot(
                {
                    "data": descriptor_rows,
                    "x_key": "name",
                    "y_key": "qed",
                    "output_path": str(run_dir / "qed_plot.png"),
                    "title": "Candidate QED scores",
                    "kind": "bar",
                }
            )
            state.add_tool_result("plotting.generate_plot", plot_result)

        filter_result = filter_molecules(
            [molecule.smiles for molecule in state.candidate_molecules],
            MoleculeFilterConstraints(max_mol_wt=500, max_logp=5.0),
        )
        state.add_tool_result("rdkit.filter_molecules", filter_result)

        if self.config.run_mode != RunMode.NO_DFT:
            if self.config.tool_enabled("xtb"):
                xtb_result = check_xtb_availability(self.config.tools.get("xtb").executable or "xtb")
                state.add_tool_result("xtb.check_availability", xtb_result)
            if self.config.tool_enabled("orca"):
                orca_tool = self.config.tools.get("orca")
                orca_result = check_orca_availability(orca_tool.executable if orca_tool else "orca")
                state.add_tool_result("orca.check_availability", orca_result)
                if state.candidate_molecules:
                    generated = run_orca(
                        {
                            "coordinates": "C 0.0 0.0 0.0\nH 0.0 0.0 1.0\nH 1.0 0.0 0.0\nH 0.0 1.0 0.0",
                            "work_dir": str(run_dir / "orca"),
                            "filename": "example.inp",
                            "executable": orca_tool.executable if orca_tool else "orca",
                            "timeout_seconds": orca_tool.timeout_seconds if orca_tool else 300,
                            "run": bool(orca_result.data.get("available")),
                        }
                    )
                    state.add_tool_result("orca.run_or_generate", generated)

        executed_count = len(state.tool_results) - initial_tool_count
        self._write_memory(
            state,
            "tools_completed",
            f"Ran {executed_count} deterministic tool calls for pass {state.iteration}.",
            node="tool_execution",
        )
        return state

    def _critic_node(self, state: DiscoveryStatePayload) -> DiscoveryStatePayload:
        logger.info("critic node")
        state = critic.run(state, config=self.config)
        decision = state.critic_decisions[-1] if state.critic_decisions else None
        reason = decision.reason if decision else "Critic completed without a recorded decision."
        self._write_memory(state, "critic_completed", reason, node="critic")
        return state

    def _writer_node(self, state: DiscoveryStatePayload) -> DiscoveryStatePayload:
        logger.info("writer node")
        state = writer.run(state)
        run_dir = _ensure_run_dir(state)
        report_path = run_dir / "report.docx"
        result = write_scientific_report(
            {
                "output_path": str(report_path),
                "user_request": state.original_user_request,
                "plan": state.plan.model_dump(mode="json") if state.plan else None,
                "candidates": [molecule.model_dump(mode="json") for molecule in state.candidate_molecules],
                "tool_results": [record.model_dump(mode="json") for record in state.tool_results],
                "critic_notes": state.critic_notes,
                "errors": state.errors,
            }
        )
        state.add_tool_result("doc_writer.write_scientific_report", result)
        if result.ok:
            state.final_report_path = result.data.get("path")
        if self.config.tool_enabled("latex_writer"):
            latex_path = run_dir / "report.tex"
            latex_result = write_latex_report(
                {
                    "output_path": str(latex_path),
                    "user_request": state.original_user_request,
                    "plan": state.plan.model_dump(mode="json") if state.plan else None,
                    "candidates": [molecule.model_dump(mode="json") for molecule in state.candidate_molecules],
                    "tool_results": [record.model_dump(mode="json") for record in state.tool_results],
                    "critic_notes": state.critic_notes,
                    "errors": state.errors,
                }
            )
            state.add_tool_result("latex_writer.write_latex_report", latex_result)
            if latex_result.ok:
                state.metadata["latex_report_path"] = latex_result.data.get("path")
        artifacts = [path for path in [state.final_report_path, state.metadata.get("latex_report_path")] if path]
        self._write_memory(
            state,
            "writer_completed",
            "Wrote final report artifacts for the discovery run.",
            node="writer",
            extra_artifacts=artifacts,
        )
        return state

    def _write_memory(
        self,
        state: DiscoveryStatePayload,
        event_type: str,
        summary: str,
        *,
        node: str,
        extra_artifacts: list[str] | None = None,
    ) -> None:
        if state.metadata.get("memory_writer_disabled"):
            return
        if not self.config.tool_enabled("memory_writer"):
            return

        tool_config = self.config.tools.get("memory_writer")
        jsonl_path = (tool_config.jsonl_path if tool_config else None) or "data/memory/project_memory.jsonl"
        markdown_path = (tool_config.markdown_path if tool_config else None) or "data/memory/project_memory.md"
        max_markdown_entries = (tool_config.max_markdown_entries if tool_config else None) or 200
        run_path = Path(state.run_dir) if state.run_dir else None
        result = append_project_memory(
            {
                "event_type": event_type,
                "summary": summary,
                "jsonl_path": jsonl_path,
                "markdown_path": markdown_path,
                "run_id": run_path.name if run_path else None,
                "run_dir": str(run_path) if run_path else None,
                "user_request": state.original_user_request,
                "node": node,
                "iteration": state.iteration,
                "run_mode": state.run_mode.value if hasattr(state.run_mode, "value") else str(state.run_mode),
                "candidate_count": len(state.candidate_molecules),
                "valid_candidate_count": state.metadata.get("valid_candidate_count"),
                "best_score": state.metadata.get("best_score"),
                "stop_reason": state.stop_reason,
                "next_actions": state.requested_next_actions,
                "artifact_paths": _artifact_paths(state, extra_artifacts),
                "recent_messages": state.messages[-5:],
                "metadata": {
                    "critic_note_count": len(state.critic_notes),
                    "error_count": len(state.errors),
                    "tool_result_count": len(state.tool_results),
                    "latest_tools": [record.tool_name for record in state.tool_results[-5:]],
                },
                "max_markdown_entries": max_markdown_entries,
            }
        )
        if result.ok:
            state.metadata["memory_jsonl_path"] = result.data.get("jsonl_path")
            if result.data.get("markdown_path"):
                state.metadata["memory_markdown_path"] = result.data.get("markdown_path")
            state.metadata["memory_event_count"] = int(state.metadata.get("memory_event_count", 0)) + 1
            return

        state.metadata["memory_writer_disabled"] = True
        state.add_error(f"memory_writer.append_project_memory: {result.error}")

    def _route_after_critic(self, raw_state: dict[str, Any]) -> str:
        return self._route_after_critic_state(DiscoveryStatePayload.model_validate(raw_state))

    def _route_after_critic_state(self, state: DiscoveryStatePayload) -> str:
        if state.needs_more_passes and state.iteration < state.max_iterations:
            return "chemist"
        if state.needs_more_passes and state.iteration >= state.max_iterations:
            state.needs_more_passes = False
            state.stop_reason = "max_iterations_reached"
            state.append_message("graph: max_iterations reached; routing to writer")
        return "writer"


def build_graph(config: AppConfig) -> DiscoveryGraph:
    return DiscoveryGraph(config)


def _ensure_run_dir(state: DiscoveryStatePayload) -> Path:
    if not state.run_dir:
        state.run_dir = str(Path("runs") / "adhoc")
    run_dir = Path(state.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _artifact_paths(state: DiscoveryStatePayload, extra_artifacts: list[str] | None = None) -> list[str]:
    paths: list[str] = []
    for record in state.tool_results:
        paths.extend(str(path) for path in record.result.artifacts)
    if state.final_report_path:
        paths.append(state.final_report_path)
    latex_path = state.metadata.get("latex_report_path")
    if latex_path:
        paths.append(str(latex_path))
    if extra_artifacts:
        paths.extend(extra_artifacts)
    return sorted(dict.fromkeys(paths))
