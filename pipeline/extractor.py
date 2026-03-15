"""
Medical entity extraction using Claude API.
Sends clinical text and receives structured entity data with suggested codes.
"""

import os
import json
from anthropic import Anthropic


EXTRACTION_PROMPT = """You are a medical entity extraction system. Given a clinical text, extract:

1. Medical entities (conditions, procedures, medications, anatomical terms)
2. For each entity, suggest:
   - The most likely ICD-10 code and its official description
   - The most likely SNOMED-CT concept ID and preferred term
   - Your confidence level (high/medium/low)
3. Return ONLY valid JSON in this format:

{
  "entities": [
    {
      "text_mention": "exact text from the input",
      "entity_type": "condition|procedure|medication|anatomy|other",
      "icd10_code": "X00.0",
      "icd10_description": "Official ICD-10 description",
      "snomed_concept_id": "123456789",
      "snomed_preferred_term": "Official SNOMED preferred term",
      "confidence": "high|medium|low"
    }
  ],
  "language_detected": "en|no"
}

Do not include entities that are not medical in nature.
Do not invent codes. If unsure of a code, set confidence to "low"."""


def extract_entities(text, api_key=None):
    """
    Send clinical text to Claude and get structured medical entities back.

    Returns a dict with 'entities' list and 'language_detected',
    or an error dict if extraction fails.
    """
    if not text or not text.strip():
        return {"entities": [], "language_detected": "unknown", "error": "Empty input"}

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {"entities": [], "error": "No API key provided"}

    try:
        client = Anthropic(api_key=key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": f"{EXTRACTION_PROMPT}\n\nClinical text:\n{text}",
                }
            ],
        )
    except Exception as e:
        error_type = type(e).__name__
        return {"entities": [], "error": f"Claude API call failed ({error_type}): {e}"}

    raw_response = ""
    for block in message.content:
        if hasattr(block, "text"):
            raw_response += block.text

    return _parse_response(raw_response)


def _parse_response(raw):
    """
    Parse the JSON response from Claude.
    Handles cases where Claude wraps JSON in markdown code fences.
    """
    cleaned = raw.strip()

    # Strip markdown code fences if present
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (the fences)
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                parsed = json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                return {"entities": [], "error": "Could not parse Claude response as JSON"}
        else:
            return {"entities": [], "error": "No JSON found in Claude response"}

    # Validate structure
    if "entities" not in parsed:
        return {"entities": [], "error": "Response missing 'entities' field"}

    # Validate each entity has required fields
    validated = []
    required_fields = ["text_mention", "entity_type"]
    for entity in parsed["entities"]:
        if all(field in entity for field in required_fields):
            validated.append(entity)

    return {
        "entities": validated,
        "language_detected": parsed.get("language_detected", "unknown"),
    }
