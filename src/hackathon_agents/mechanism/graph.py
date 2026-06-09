from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Literal

from hackathon_agents.mechanism.experiment_design import ActiveLearningPolicy, RLExperimentDesigner
from hackathon_agents.mechanism.hypothesis import generate_hypothesis_json, validate_hypothesis_json
from hackathon_agents.mechanism.kinetic_fitting import fit_all_hypotheses
from hackathon_agents.mechanism.reporting import write_mechanism_report
from hackathon_agents.mechanism.state import MechanismDiscoveryState, MechanismRunMode
from hackathon_agents.mechanism.uncertainty import build_critic_assessment, rank_hypotheses
from hackathon_agents.tools.dft_job import DFTCalculationType, DFTJob, DFTResult
from hackathon_agents.tools.hpc_client import HPCClient, MockHPCClient, SlurmHPCClient
from hackathon_agents.tools.kinetics_io import parse_kinetics_file, write_kinetic_dataset
from hackathon_agents.tools.literature_search import search_literature_prior
from hackathon_agents.tools.robot_client import HTTPRobotClient, MockRobotClient, RobotClient

logger = logging.getLogger(__name__)


class MechanismDiscoveryGraph:
    """Bounded closed-loop graph for mechanism discovery from kinetic data."""

    def __init__(
        self,
        *,
        robot_client: RobotClient | None = None,
        hpc_client: HPCClient | None = None,
        experiment_designer: ActiveLearningPolicy | None = None,
    ):
        self.robot_client = robot_client or MockRobotClient()
        self.hpc_client = hpc_client or MockHPCClient()
        self.experiment_designer = experiment_designer or RLExperimentDesigner()

    @classmethod
    def from_mode(
        cls,
        *,
        mode: MechanismRunMode,
        run_dir: Path,
        allow_real_robot: bool = False,
        allow_hpc_submit: bool = False,
        robot_base_url: str | None = None,
        robot_api_key: str | None = None,
    ) -> "MechanismDiscoveryGraph":
        """Create clients for mock, dry-run, or explicitly enabled real mode."""

        if mode == "real":
            if not allow_real_robot:
                raise ValueError("real robot mode requires allow_real_robot=True")
            if not robot_base_url:
                raise ValueError("real robot mode requires robot_base_url")
            robot_client: RobotClient = HTTPRobotClient(
                base_url=robot_base_url,
                api_key=robot_api_key,
                allow_real_submissions=allow_real_robot,
            )
            hpc_client: HPCClient = SlurmHPCClient(
                submit_dir=run_dir / "dft_jobs",
                allow_submit=allow_hpc_submit,
            )
        elif mode == "dry-run":
            robot_client = MockRobotClient(noise_level=0.0)
            hpc_client = SlurmHPCClient(submit_dir=run_dir / "dft_jobs", allow_submit=False)
        else:
            robot_client = MockRobotClient()
            hpc_client = MockHPCClient()
        return cls(robot_client=robot_client, hpc_client=hpc_client)

    def run_loop(
        self,
        *,
        objective: str,
        rounds: int,
        run_dir: str | Path,
        mode: MechanismRunMode = "mock",
    ) -> MechanismDiscoveryState:
        """Run the bounded closed-loop mechanism workflow."""

        if rounds < 1:
            raise ValueError("rounds must be at least 1")
        state = MechanismDiscoveryState(
            objective=objective,
            mode=mode,
            run_dir=str(run_dir),
            max_rounds=rounds,
        )
        handler = _attach_trace_log(Path(run_dir))
        trace_logger = logging.getLogger("hackathon_agents.mechanism.trace")
        try:
            self._literature_agent(state)
            self._hypothesis_agent(state)
            for round_index in range(rounds):
                state.round_index = round_index + 1
                trace_logger.info("starting mechanism loop round %s/%s", state.round_index, rounds)
                experiment = self._rl_experiment_designer(state, round_index=round_index)
                state.next_experiment = experiment
                state.experiments.append(experiment)
                robot_job_id = self._robot_agent(state, experiment)
                dataset = self._data_ingestion_agent(state, robot_job_id)
                if dataset is not None:
                    state.datasets.append(dataset)
                    state.fit_results.extend(self._kinetic_model_agent(state, dataset))
                    state.rankings = rank_hypotheses(state.hypotheses, state.fit_results)
                self._dft_agent(state)
                self._critic_agent(state, experiment)
                self._save_round_artifacts(state)
            return state
        finally:
            trace_logger.removeHandler(handler)
            handler.close()

    def run_once(
        self,
        *,
        objective: str,
        data_path: str | Path,
        run_dir: str | Path,
        mode: MechanismRunMode = "mock",
    ) -> MechanismDiscoveryState:
        """Run one analysis pass on an existing kinetic dataset."""

        state = MechanismDiscoveryState(
            objective=objective,
            mode=mode,
            run_dir=str(run_dir),
            max_rounds=1,
            round_index=1,
        )
        handler = _attach_trace_log(Path(run_dir))
        trace_logger = logging.getLogger("hackathon_agents.mechanism.trace")
        try:
            trace_logger.info("starting mechanism-once analysis for %s", data_path)
            self._literature_agent(state)
            self._hypothesis_agent(state)
            dataset = parse_kinetics_file(data_path)
            state.datasets.append(dataset)
            state.fit_results.extend(self._kinetic_model_agent(state, dataset))
            state.rankings = rank_hypotheses(state.hypotheses, state.fit_results)
            state.next_experiment = self._rl_experiment_designer(state, round_index=0)
            self._dft_agent(state)
            self._critic_agent(state, state.next_experiment)
            self._save_round_artifacts(state)
            return state
        finally:
            trace_logger.removeHandler(handler)
            handler.close()

    def _literature_agent(self, state: MechanismDiscoveryState) -> None:
        state.literature_prior = search_literature_prior(state.objective, mode=state.mode)

    def _hypothesis_agent(self, state: MechanismDiscoveryState) -> None:
        raw_json = generate_hypothesis_json(state.objective, state.literature_prior)
        try:
            state.hypotheses = validate_hypothesis_json(raw_json, retry_json=raw_json)
        except ValueError as exc:
            state.add_validation_error(str(exc))
            state.hypotheses = []

    def _kinetic_model_agent(self, state: MechanismDiscoveryState, dataset) -> list:
        return fit_all_hypotheses(state.hypotheses, dataset)

    def _rl_experiment_designer(self, state: MechanismDiscoveryState, *, round_index: int):
        return self.experiment_designer.propose_next_experiment(
            objective=state.objective,
            hypotheses=state.hypotheses,
            rankings=state.rankings,
            round_index=round_index,
        )

    def _robot_agent(self, state: MechanismDiscoveryState, experiment) -> str:
        try:
            job_id = self.robot_client.submit_experiment(experiment)
            state.robot_jobs.append(job_id)
            return job_id
        except Exception as exc:
            state.add_error(f"RobotAgent failed to submit experiment {experiment.id}: {exc}")
            return ""

    def _data_ingestion_agent(self, state: MechanismDiscoveryState, job_id: str):
        if not job_id:
            return None
        try:
            status = self.robot_client.get_status(job_id)
            if status not in {"completed", "succeeded", "done"}:
                state.add_error(f"Robot job {job_id} is not complete: {status}")
                return None
            result = self.robot_client.fetch_results(job_id)
            if isinstance(result, (str, Path)):
                return parse_kinetics_file(result)
            return result
        except Exception as exc:
            state.add_error(f"DataIngestionAgent failed for robot job {job_id}: {exc}")
            return None

    def _dft_agent(self, state: MechanismDiscoveryState) -> None:
        if not state.rankings:
            return
        top = state.rankings[0]
        if top.uncertainty < 0.35:
            return
        if any(job.linked_hypothesis_id == top.hypothesis_id for job in state.dft_jobs):
            return
        hypothesis = next((candidate for candidate in state.hypotheses if candidate.id == top.hypothesis_id), None)
        if hypothesis is None or not hypothesis.dft_requirements:
            return
        job = DFTJob(
            id=f"dft-{top.hypothesis_id}-r{state.round_index:03d}",
            molecule_or_structure="C 0.000 0.000 0.000\nH 0.000 0.000 1.089\nH 1.026 0.000 -0.363\nH -0.513 0.889 -0.363\nH -0.513 -0.889 -0.363",
            charge=0,
            multiplicity=1,
            method="B3LYP",
            basis="def2-SVP",
            solvent_model="MeCN",
            calculation_type=DFTCalculationType.SINGLE_POINT,
            reason_for_calculation=hypothesis.dft_requirements[0],
            linked_hypothesis_id=hypothesis.id,
        )
        state.dft_jobs.append(job)
        try:
            job_id = self.hpc_client.submit_job(job)
            state.hpc_jobs.append(job_id)
            status = self.hpc_client.get_status(job_id)
            if status in {"completed", "script_written", "submitted"}:
                state.dft_results.append(self.hpc_client.fetch_results(job_id))
        except Exception as exc:
            state.add_error(f"DFTAgent failed for {job.id}: {exc}")

    def _critic_agent(self, state: MechanismDiscoveryState, experiment) -> None:
        assessment = build_critic_assessment(
            round_index=state.round_index,
            rankings=state.rankings,
            fit_results=state.fit_results,
            experiment=experiment,
            dft_jobs=state.dft_jobs,
        )
        state.critic_assessments.append(assessment)
        for category in (
            assessment.plausibility_notes,
            assessment.overfitting_notes,
            assessment.identifiability_notes,
            assessment.missing_controls,
            assessment.dft_notes,
            assessment.robot_feasibility_notes,
        ):
            state.critic_notes.extend(category)

    def _save_round_artifacts(self, state: MechanismDiscoveryState) -> None:
        if state.run_path is None:
            raise ValueError("run_dir is required")
        run_dir = state.run_path
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "hypotheses.json").write_text(
            json.dumps([hypothesis.model_dump(mode="json") for hypothesis in state.hypotheses], indent=2),
            encoding="utf-8",
        )
        (run_dir / "experiments.json").write_text(
            json.dumps([experiment.model_dump(mode="json") for experiment in state.experiments], indent=2),
            encoding="utf-8",
        )
        datasets_dir = run_dir / "datasets"
        for dataset in state.datasets:
            write_kinetic_dataset(dataset, datasets_dir)
        dft_dir = run_dir / "dft_jobs"
        dft_dir.mkdir(parents=True, exist_ok=True)
        for job in state.dft_jobs:
            (dft_dir / f"{job.id}.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")
        for result in state.dft_results:
            (dft_dir / f"{result.job_id}_result.json").write_text(
                result.model_dump_json(indent=2),
                encoding="utf-8",
            )
        write_mechanism_report(state)
        state.save_json(run_dir / "state.json")


def run_mechanism_loop(
    *,
    objective: str,
    rounds: int,
    mode: MechanismRunMode = "mock",
    run_root: str | Path = "runs",
    allow_real_robot: bool = False,
    allow_hpc_submit: bool = False,
    robot_base_url: str | None = None,
    robot_api_key: str | None = None,
) -> MechanismDiscoveryState:
    """Convenience entrypoint for the closed-loop CLI command."""

    run_dir = _new_run_dir(run_root, "mechanism")
    graph = MechanismDiscoveryGraph.from_mode(
        mode=mode,
        run_dir=run_dir,
        allow_real_robot=allow_real_robot,
        allow_hpc_submit=allow_hpc_submit,
        robot_base_url=robot_base_url,
        robot_api_key=robot_api_key,
    )
    return graph.run_loop(objective=objective, rounds=rounds, run_dir=run_dir, mode=mode)


def run_mechanism_once(
    *,
    objective: str,
    data_path: str | Path,
    mode: Literal["mock", "dry-run", "real"] = "mock",
    run_root: str | Path = "runs",
) -> MechanismDiscoveryState:
    """Convenience entrypoint for one-pass analysis of existing data."""

    run_dir = _new_run_dir(run_root, "mechanism_once")
    graph = MechanismDiscoveryGraph.from_mode(mode=mode, run_dir=run_dir)
    return graph.run_once(objective=objective, data_path=data_path, run_dir=run_dir, mode=mode)


def _new_run_dir(run_root: str | Path, prefix: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(run_root) / f"{prefix}_{timestamp}"
    suffix = 1
    while run_dir.exists():
        suffix += 1
        run_dir = Path(run_root) / f"{prefix}_{timestamp}_{suffix}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _attach_trace_log(run_dir: Path) -> logging.Handler:
    run_dir.mkdir(parents=True, exist_ok=True)
    trace_logger = logging.getLogger("hackathon_agents.mechanism.trace")
    trace_logger.setLevel(logging.INFO)
    handler = logging.FileHandler(run_dir / "trace.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    trace_logger.addHandler(handler)
    trace_logger.propagate = False
    return handler
