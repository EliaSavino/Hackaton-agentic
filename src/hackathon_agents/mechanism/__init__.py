"""Mechanism discovery workflow for closed-loop kinetic experiments.

This package is intentionally additive to the generic hackathon scaffold.  It
contains typed state, schema-validated agent outputs, deterministic mock tools,
and a bounded graph for autonomous mechanism discovery from kinetic data.
"""

from hackathon_agents.mechanism.graph import MechanismDiscoveryGraph, run_mechanism_loop, run_mechanism_once
from hackathon_agents.mechanism.state import MechanismDiscoveryState

__all__ = [
    "MechanismDiscoveryGraph",
    "MechanismDiscoveryState",
    "run_mechanism_loop",
    "run_mechanism_once",
]
