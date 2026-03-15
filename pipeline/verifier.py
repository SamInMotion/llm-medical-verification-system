"""
Pipeline orchestration for MedTermCheck.
Coordinates extraction, ontology verification, and confidence scoring.
"""

from ontology.icd_lookup import ICDLookup
from ontology.snomed_client import SNOMEDClient
from pipeline.extractor import extract_entities
from pipeline.confidence import score_entity

_icd = None
_snomed = None


def _get_icd():
    global _icd
    if _icd is None:
        _icd = ICDLookup(data_dir="data")
    return _icd


def _get_snomed():
    global _snomed
    if _snomed is None:
        _snomed = SNOMEDClient()
    return _snomed


def verify_text(text, api_key=None):
    extraction = extract_entities(text, api_key=api_key)

    if extraction.get("error"):
        return {
            "verified_entities": [],
            "summary": {"total": 0, "error": extraction["error"]},
            "language": extraction.get("language_detected", "unknown"),
        }

    entities = extraction.get("entities", [])
    if not entities:
        return {
            "verified_entities": [],
            "summary": {"total": 0, "grounded": 0, "partial": 0, "ungrounded": 0},
            "language": extraction.get("language_detected", "unknown"),
        }

    icd = _get_icd()
    snomed = _get_snomed()

    verified = []
    for entity in entities:
        icd_code = entity.get("icd10_code", "")
        entity_term = entity.get("snomed_preferred_term", "") or entity.get("text_mention", "")

        icd_result = icd.lookup(icd_code) if icd_code else {"found": False}
        snomed_result = snomed.verify_term(entity_term) if entity_term else {"found": False}

        scoring = score_entity(entity, icd_result, snomed_result, text)

        verified.append({
            "text_mention": entity.get("text_mention", ""),
            "entity_type": entity.get("entity_type", ""),
            "icd10": {
                "code": icd_code,
                "llm_description": entity.get("icd10_description", ""),
                "verified_description": icd_result.get("description", ""),
                "match_type": icd_result.get("match_type", "none"),
                "found": icd_result.get("found", False),
            },
            "snomed": {
                "concept_id": entity.get("snomed_concept_id", ""),
                "llm_term": entity.get("snomed_preferred_term", ""),
                "verified_term": snomed_result.get("preferred_term", ""),
                "found": snomed_result.get("found", False),
                "source": snomed_result.get("source", ""),
            },
            "confidence": scoring,
        })

    statuses = [v["confidence"]["status"] for v in verified]
    summary = {
        "total": len(verified),
        "grounded": statuses.count("Grounded"),
        "partial": statuses.count("Partial"),
        "ungrounded": statuses.count("Ungrounded"),
        "avg_score": round(
            sum(v["confidence"]["score"] for v in verified) / len(verified), 2
        ) if verified else 0,
    }

    metadata = {
        "icd10_codes_loaded": icd.code_count(),
        "icd10_using_fallback": icd.is_fallback(),
        "snomed_api_available": snomed.is_api_available(),
    }

    return {
        "verified_entities": verified,
        "summary": summary,
        "language": extraction.get("language_detected", "unknown"),
        "metadata": metadata,
    }