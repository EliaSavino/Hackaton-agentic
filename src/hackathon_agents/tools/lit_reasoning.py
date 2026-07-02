"""Phase A — Autonomous literature reasoning.

Queries the RAG database (rag.sqlite), extracts exemplars, and dynamically derives
design rules using the LLM.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hackathon_agents.rag import RAGStore, DEFAULT_RAG_DB_PATH
from hackathon_agents.llm.client import LLMClient, CompletionRequest
from hackathon_agents.config import AppConfig
from hackathon_agents.logging_config import get_logger

logger = get_logger(__name__)

def derive_literature_rules(
    payload_class: str,
    config: AppConfig,
    db_path: Path | str = DEFAULT_RAG_DB_PATH,
) -> dict[str, Any]:
    """Retrieve articles from RAG, extract exemplars, and derive design rules."""
    logger.info("Deriving literature rules for payload class: %s", payload_class)
    store = RAGStore(db_path)
    client = LLMClient(config)
    
    # 1. Retrieve relevant literature chunks
    query = f"linker designs and guidelines for {payload_class} payload conjugates"
    context = store.build_context(query, limit=12, max_chars=12000)
    retrieved_text = context.get("context", "")
    
    if not retrieved_text:
        logger.warning("No literature found in RAG store. Using built-in default guidelines.")
        retrieved_text = "Standard clinical conjugates utilize Val-Cit-PABC or SMCC."
        
    # 2. Extractor Prompt
    extractor_prompt = f"""You are a senior literature curation bot. Analyze the following retrieved literature snippets and extract a list of counterparty/conjugate exemplars for '{payload_class}' payloads.
For each conjugate, extract:
- Payload name (e.g. MMAE, siRNA, R848)
- Linker architecture (e.g. Val-Cit-PABC, sulfo-SMCC)
- Conjugation chemistry (e.g. maleimide, DBCO click)
- Cleavage mechanism (e.g. cathepsin-B protease, non-cleavable)
- Plasma stability (e.g. high, moderate, low)
- Release trigger
- Citation/source

Retrieved Literature:
{retrieved_text}

Provide the output as a valid JSON list of objects under the key 'exemplars'. Format exactly:
{{
  "exemplars": [
     {{
       "payload": "MMAE",
       "linker": "Val-Cit-PABC",
       "conjugation": "maleimide cysteine",
       "cleavage": "protease-cleavable",
       "plasma_stability": "high",
       "trigger": "cathepsin-B",
       "citation": "siRNA.pdf / reviews"
     }}
  ]
}}
"""
    # Use the science reasoning model or local fallback
    response = client.complete(
        CompletionRequest(
            model_alias="science_reasoning",
            messages=[
                {"role": "system", "content": "You are an expert bio-curator. Output raw JSON only."},
                {"role": "user", "content": extractor_prompt}
            ],
            temperature=0.0,
            max_tokens=2000,
        )
    )
    
    exemplars = []
    if response.ok:
        try:
            # Clean JSON markers if present
            clean_content = response.content.strip()
            if "```json" in clean_content:
                clean_content = clean_content.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_content:
                clean_content = clean_content.split("```")[1].split("```")[0].strip()
            parsed = json.loads(clean_content)
            exemplars = parsed.get("exemplars", [])
        except Exception as exc:
            logger.warning("Failed to parse extracted exemplars JSON: %s. Using default list.", exc)
            
    if not exemplars:
        # Structured fallbacks depending on payload_class
        if payload_class == "cytotoxin":
            exemplars = [
                {"payload": "MMAE", "linker": "Val-Cit-PABC", "conjugation": "maleimide", "cleavage": "protease-cleavable", "plasma_stability": "high", "trigger": "cathepsin-B", "citation": "Internal Reference"},
                {"payload": "DM1", "linker": "SMCC", "conjugation": "maleimide thioether", "cleavage": "non-cleavable", "plasma_stability": "very high", "trigger": "lysosomal catabolism", "citation": "Internal Reference"}
            ]
        elif payload_class == "oligonucleotide":
            exemplars = [
                {"payload": "siRNA", "linker": "sulfo-SMCC", "conjugation": "ThioMab cysteine", "cleavage": "non-cleavable", "plasma_stability": "extremely high", "trigger": "none (intracellular active as intact)", "citation": "siRNA.pdf"}
            ]
        else:
            exemplars = [
                {"payload": "R848 (imidazoquinoline)", "linker": "Val-Ala-PAB", "conjugation": "DBCO", "cleavage": "protease-cleavable", "plasma_stability": "very high", "trigger": "cathepsin-B", "citation": "Internal Reference"}
            ]

    # 3. Rule Derivation Prompt
    derivation_prompt = f"""You are a molecular design oracle. Based on the following exemplars extracted from the literature for the payload class '{payload_class}', derive the core design rules.
Exemplars:
{json.dumps(exemplars, indent=2)}

Determine:
1. Cleavage preference (e.g. protease-cleavable, non-cleavable-rigid, non-cleavable-flexible)
2. Structural rigidity (e.g. rigid, flexible, semi-rigid)
3. Plasma stability priority (e.g. high, maximum)
4. Recommended conjugation handles
5. Solubilizing group requirements

Provide the output as a valid JSON object. Format exactly:
{{
  "cleavage_preference": "protease-cleavable",
  "rigidity": "semi-rigid",
  "stability_priority": "high",
  "conjugation_recommendation": ["maleimide", "DBCO"],
  "solubilizing_requirements": ["PEG", "zwitterion"],
  "rationale": "Write a 2-sentence rationale summarizing the literature findings."
}}
"""
    response_rules = client.complete(
        CompletionRequest(
            model_alias="frontier_reasoning",
            messages=[
                {"role": "system", "content": "You are an expert chemist. Output raw JSON only."},
                {"role": "user", "content": derivation_prompt}
            ],
            temperature=0.1,
            max_tokens=1500,
        )
    )
    
    rules = {}
    if response_rules.ok:
        try:
            clean_content = response_rules.content.strip()
            if "```json" in clean_content:
                clean_content = clean_content.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_content:
                clean_content = clean_content.split("```")[1].split("```")[0].strip()
            rules = json.loads(clean_content)
        except Exception as exc:
            logger.warning("Failed to parse derived rules JSON: %s. Using default rules.", exc)
            
    if not rules:
        if payload_class == "cytotoxin":
            rules = {
                "cleavage_preference": "protease-cleavable",
                "rigidity": "semi-rigid",
                "stability_priority": "high",
                "conjugation_recommendation": ["maleimide"],
                "solubilizing_requirements": ["PEG"],
                "rationale": "Cytotoxins generally require rapid, traceless lysosomal release (e.g. Val-Cit-PABC) to ensure robust cell killing, balanced with moderate hydrophilicity to reduce aggregation."
            }
        elif payload_class == "oligonucleotide":
            rules = {
                "cleavage_preference": "non-cleavable-rigid",
                "rigidity": "rigid",
                "stability_priority": "maximum",
                "conjugation_recommendation": ["ThioMab click"],
                "solubilizing_requirements": ["PEG", "sulfo"],
                "rationale": "Oligonucleotides are large, highly anionic, and stable. Literature (siRNA.pdf) shows that rigid non-cleavable linkers like sulfo-SMCC outperform flexible ones by maintaining structural integrity and preventing premature systemic loss."
            }
        else: # immunomodulator
            rules = {
                "cleavage_preference": "protease-cleavable",
                "rigidity": "semi-rigid",
                "stability_priority": "maximum",
                "conjugation_recommendation": ["DBCO", "maleimide"],
                "solubilizing_requirements": ["PEG"],
                "rationale": "Immunomodulators require highly plasma-stable triggers such as Val-Ala-PABC to avoid systemic cytokine storm, demanding slow but clean intracellular release."
            }
            
    return {
        "payload_class": payload_class,
        "exemplars": exemplars,
        "rules": rules,
        "retrieved_evidence": retrieved_text[:1000] + "..."
    }
