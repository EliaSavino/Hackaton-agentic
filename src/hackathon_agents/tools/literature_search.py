from __future__ import annotations

import os

from hackathon_agents.mechanism.schemas import LiteraturePrior
from hackathon_agents.tools.literature_tools import search_local_corpus


MOCK_LITERATURE_TEXT = """
Photochemical and radical mechanisms can show strong light-intensity effects,
dark-control suppression, inhibitor sensitivity, and non-integer apparent
reaction orders. Catalytic mechanisms can be obscured by product inhibition,
off-cycle catalyst deactivation, or mass-transfer-limited apparent kinetics.
Kinetic controls should vary photon flux, catalyst loading, substrate
concentration, residence time, and added product independently.
""".strip()


def search_literature_prior(
    objective: str,
    *,
    mode: str = "mock",
    local_text: str | None = None,
    corpus_dir: str | None = None,
    limit: int = 5,
) -> LiteraturePrior:
    """Return literature context with a mock/local implementation by default."""

    local_corpus_dir = corpus_dir or os.getenv("MECHANISM_LITERATURE_CORPUS_DIR")
    if local_corpus_dir:
        result = search_local_corpus({"query": objective, "corpus_dir": local_corpus_dir, "limit": limit})
        if result.ok and result.data.get("records"):
            records = result.data["records"]
            snippets = [record.get("snippet", "") for record in records if record.get("snippet")]
            citations = [
                str(record.get("path") or record.get("title") or f"local-record-{index}")
                for index, record in enumerate(records, start=1)
            ]
            return LiteraturePrior(
                query=objective,
                summary="\n".join(snippets)[:4000],
                key_findings=snippets[:5],
                citations=citations,
                limitations=[
                    "Local lexical retrieval is a prior, not proof of mechanism.",
                    "Evidence quality depends on the supplied local corpus.",
                ],
                source="local",
            )

    text = local_text or MOCK_LITERATURE_TEXT
    if mode == "mock":
        source = "mock"
        citations = ["mock:photochemical-kinetics-prior", "mock:catalyst-deactivation-prior"]
    elif mode == "dry-run":
        source = "dry-run"
        citations = []
    else:
        source = "local"
        citations = []
    return LiteraturePrior(
        query=objective,
        summary=text,
        key_findings=[
            "Light-intensity and dark controls are diagnostic for photoredox or radical pathways.",
            "Added product and catalyst-age controls can expose inhibition or deactivation.",
            "Flow-rate and residence-time perturbations can distinguish intrinsic and transport-limited kinetics.",
        ],
        citations=citations,
        limitations=[
            "Mock literature prior is not evidence for the specific reaction.",
            "No external literature API is queried unless a project-specific implementation is added.",
        ],
        source=source,
    )
