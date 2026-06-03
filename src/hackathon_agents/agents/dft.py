from __future__ import annotations

from hackathon_agents.state import DiscoveryStatePayload


def run(state: DiscoveryStatePayload) -> DiscoveryStatePayload:
    state.append_message("dft: delegated to xTB and ORCA tool wrappers")
    return state
