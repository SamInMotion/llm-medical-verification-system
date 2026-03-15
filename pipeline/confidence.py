"""
Confidence scoring for verified medical entities.

Uses four independent signals to produce a reproducible score.
Every score can be reconstructed from the evidence dictionary alone.
No black-box probability model. This matters for regulated-domain
audit tools where reproducibility is the point.

Weight rationale:
- ICD-10 (0.30): Primary structured ontology. Exact code match is strong evidence.
- SNOMED-CT (0.30): Second independent ontology. Confirms the concept exists
  in a different knowledge system.
- Source text grounding (0.20): Checks that the entity actually appears in the
  input text. Prevents false positive extractions where the LLM invents entities.
- LLM self-reported confidence (0.10): Weakest signal because the LLM is the
  system being audited. Its own confidence estimate is the least trustworthy input.
- Bonus (0.10): Awarded when both ontologies confirm AND the entity is grounded
  in source text. This rewards convergent evidence.
"""

from rapidfuzz import fuzz

WEIGHT_ICD = 0.30
WEIGHT_SNOMED = 0.30
WEIGHT_SOURCE = 0.20
WEIGHT_LLM = 0.10
WEIGHT_BONUS = 0.10

CONFIDENCE_MAP = {"high": 1.0, "medium": 0.6, "low": 0.3}

# Threshold for fuzzy matching entity mentions against source text
FUZZY_THRESHOLD = 70


def score_entity(entity, icd_result, snomed_result, source_text):
    """
    Compute a confidence score for a single verified entity.

    Arguments:
        entity: dict from Claude extraction (text_mention, icd10_code, confidence, etc.)
        icd_result: dict from ICDLookup.lookup()
        snomed_result: dict from SNOMEDClient.verify_term()
        source_text: the original input text

    Returns:
        dict with score (0.0-1.0), status label, and detailed evidence breakdown.
    """
    evidence = {}

    # Signal 1: ICD-10 verification
    icd_score = 0.0
    if icd_result.get("found"):
        match_type = icd_result.get("match_type", "")
        if match_type == "exact":
            icd_score = 1.0
            evidence["icd10"] = "exact match"
        elif match_type == "parent":
            icd_score = 0.6
            evidence["icd10"] = f"parent match ({icd_result.get('code', '')})"
        else:
            icd_score = 0.8
            evidence["icd10"] = "found"
    else:
        evidence["icd10"] = "not found"

    # Signal 2: SNOMED-CT verification
    snomed_score = 0.0
    if snomed_result.get("found"):
        snomed_score = 1.0
        preferred = snomed_result.get("preferred_term", "")
        concept_id = snomed_result.get("conceptId", "")
        evidence["snomed"] = f"confirmed ({concept_id}: {preferred})"
    else:
        evidence["snomed"] = "not found"

    # Signal 3: Source text grounding
    source_score = 0.0
    mention = entity.get("text_mention", "")
    if mention and source_text:
        ratio = fuzz.partial_ratio(mention.lower(), source_text.lower())
        if ratio >= FUZZY_THRESHOLD:
            source_score = 1.0
            evidence["source_grounding"] = f"found in text (match: {ratio}%)"
        else:
            source_score = 0.0
            evidence["source_grounding"] = f"weak match ({ratio}%)"
    else:
        evidence["source_grounding"] = "no text to compare"

    # Signal 4: LLM self-reported confidence (weakest signal)
    llm_conf_raw = entity.get("confidence", "low")
    llm_score = CONFIDENCE_MAP.get(llm_conf_raw, 0.3)
    evidence["llm_confidence"] = llm_conf_raw

    # Bonus: convergent evidence from multiple sources
    bonus = 0.0
    if icd_score >= 0.8 and snomed_score >= 0.8 and source_score >= 0.8:
        bonus = 1.0
        evidence["convergent_bonus"] = "all three verification sources agree"

    # Weighted sum
    total = (
        WEIGHT_ICD * icd_score
        + WEIGHT_SNOMED * snomed_score
        + WEIGHT_SOURCE * source_score
        + WEIGHT_LLM * llm_score
        + WEIGHT_BONUS * bonus
    )
    total = min(total, 1.0)
    total = round(total, 2)

    # Status label
    status = _assign_status(icd_score, snomed_score, total)
    evidence["status"] = status

    return {
        "score": total,
        "status": status,
        "evidence": evidence,
        "signal_breakdown": {
            "icd10": round(WEIGHT_ICD * icd_score, 3),
            "snomed": round(WEIGHT_SNOMED * snomed_score, 3),
            "source": round(WEIGHT_SOURCE * source_score, 3),
            "llm": round(WEIGHT_LLM * llm_score, 3),
            "bonus": round(WEIGHT_BONUS * bonus, 3),
        },
    }


def _assign_status(icd_score, snomed_score, total):
    """
    Assign a human-readable status label.

    Grounded: both ICD-10 and SNOMED confirm the entity.
    Partial: one ontology confirms, or parent code match.
    Ungrounded: neither ontology confirms.
    """
    if icd_score >= 0.8 and snomed_score >= 0.8:
        return "Grounded"
    if icd_score >= 0.6 or snomed_score >= 0.6:
        return "Partial"
    return "Ungrounded"


def status_emoji(status):
    """Return a plain text indicator for each status level."""
    # Using text markers instead of emoji per code style guidelines
    if status == "Grounded":
        return "[OK]"
    if status == "Partial":
        return "[??]"
    return "[XX]"
