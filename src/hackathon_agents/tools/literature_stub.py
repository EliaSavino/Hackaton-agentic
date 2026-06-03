from __future__ import annotations

from hackathon_agents.tools.base import ok_result


def search_literature_stub(query: str, limit: int = 5):
    records = [
        {
            "title": "Placeholder literature result",
            "abstract": "Offline stub. Replace with a real retriever when internet or a local corpus is available.",
            "query": query,
        }
        for _ in range(max(1, limit))
    ]
    return ok_result({"records": records, "offline_stub": True})
