from __future__ import annotations

from hackathon_agents.state import DiscoveryStatePayload


def run(state: DiscoveryStatePayload) -> DiscoveryStatePayload:
    state.append_message("writer: report generation delegated to doc_writer and latex_writer tools")
    return state
