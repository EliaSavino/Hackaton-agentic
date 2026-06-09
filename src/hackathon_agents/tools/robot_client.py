from __future__ import annotations

from abc import ABC, abstractmethod
from itertools import count
from typing import Any

from hackathon_agents.mechanism.kinetic_fitting import simulate_kinetic_dataset
from hackathon_agents.mechanism.mechanism_classes import MechanismClass
from hackathon_agents.mechanism.schemas import KineticDataset, KineticExperiment


class RobotClient(ABC):
    """Abstract robot interface used by RobotAgent."""

    @abstractmethod
    def submit_experiment(self, protocol: KineticExperiment | dict[str, Any]) -> str:
        """Submit a robot protocol and return a job identifier."""

    @abstractmethod
    def get_status(self, job_id: str) -> str:
        """Return current job status."""

    @abstractmethod
    def fetch_results(self, job_id: str) -> KineticDataset | str:
        """Return parsed results or a path to a result file."""


class MockRobotClient(RobotClient):
    """Offline robot client that generates synthetic kinetic traces."""

    def __init__(
        self,
        *,
        hidden_mechanism: MechanismClass = MechanismClass.PHOTOREDOX_CATALYTIC_CYCLE,
        noise_level: float = 0.005,
    ):
        self.hidden_mechanism = hidden_mechanism
        self.noise_level = noise_level
        self._ids = count(1)
        self._jobs: dict[str, KineticExperiment] = {}
        self._results: dict[str, KineticDataset] = {}

    def submit_experiment(self, protocol: KineticExperiment | dict[str, Any]) -> str:
        experiment = protocol if isinstance(protocol, KineticExperiment) else KineticExperiment.model_validate(protocol)
        job_id = f"robot-mock-{next(self._ids):04d}"
        self._jobs[job_id] = experiment
        seed = 100 + len(self._jobs)
        self._results[job_id] = simulate_kinetic_dataset(
            experiment,
            mechanism_class=self.hidden_mechanism,
            noise_level=self.noise_level,
            seed=seed,
        )
        return job_id

    def get_status(self, job_id: str) -> str:
        return "completed" if job_id in self._results else "unknown"

    def fetch_results(self, job_id: str) -> KineticDataset:
        if job_id not in self._results:
            raise KeyError(f"unknown mock robot job: {job_id}")
        return self._results[job_id]


class HTTPRobotClient(RobotClient):
    """Placeholder HTTP robot client.

    The implementation is intentionally inert unless real submission is
    explicitly enabled by CLI/config.  Projects can extend this class with their
    robot scheduler's authentication, payload shape, and polling semantics.
    """

    def __init__(self, *, base_url: str, api_key: str | None = None, allow_real_submissions: bool = False):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.allow_real_submissions = allow_real_submissions

    def submit_experiment(self, protocol: KineticExperiment | dict[str, Any]) -> str:
        if not self.allow_real_submissions:
            raise RuntimeError("real robot submission is disabled; use --allow-real-robot to opt in")
        raise NotImplementedError("HTTPRobotClient is a placeholder; implement project-specific POST semantics")

    def get_status(self, job_id: str) -> str:
        if not self.allow_real_submissions:
            return "dry-run-disabled"
        raise NotImplementedError("HTTPRobotClient status polling is project-specific")

    def fetch_results(self, job_id: str) -> KineticDataset | str:
        if not self.allow_real_submissions:
            raise RuntimeError("real robot result fetching is disabled")
        raise NotImplementedError("HTTPRobotClient result fetching is project-specific")
