from __future__ import annotations

from hackathon_agents.state import DiscoveryStatePayload


def run(state: DiscoveryStatePayload) -> DiscoveryStatePayload:
    state.append_message("coder: no code generation required for deterministic scaffold")
    return state
