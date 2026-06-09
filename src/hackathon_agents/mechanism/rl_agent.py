from __future__ import annotations

from hackathon_agents.mechanism.experiment_design import ActiveLearningPolicy, RLExperimentDesigner


class PlaceholderRLPolicy:
    """Documented hook for replacing the heuristic with a trained policy."""

    def __init__(self, policy_uri: str):
        self.policy_uri = policy_uri

    def propose_next_experiment(self, **_: object):
        """Raise until a concrete policy backend is connected."""

        raise NotImplementedError(
            f"No RL policy backend is connected for {self.policy_uri!r}; use RLExperimentDesigner for mock mode."
        )


__all__ = ["ActiveLearningPolicy", "RLExperimentDesigner", "PlaceholderRLPolicy"]
