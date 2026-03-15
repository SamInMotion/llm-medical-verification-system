"""
MedTermCheck: Ontology-Grounded Verification for LLM Medical Outputs.

Gradio interface for verifying medical entities extracted by LLMs
against SNOMED-CT and ICD-10 ontologies.
"""

import os
import gradio as gr
from pipeline.verifier import verify_text

EXAMPLES = [
    [
        "The patient was diagnosed with type 2 diabetes mellitus and essential "
        "hypertension. She was prescribed metformin 500mg twice daily. "
        "Blood glucose levels were elevated at 250 mg/dL.",
        "",
    ],
    [
        "A 67-year-old male presents with worsening dyspnea and productive cough. "
        "Chest X-ray reveals bilateral infiltrates consistent with pneumonia. "
        "He has a history of COPD and atrial fibrillation.",
        "",
    ],
    [
        "Pasienten ble innlagt med mistanke om sepsis. Blodkulturer viste vekst "
        "av E. coli. CRP var kraftig forhøyet. Han ble behandlet med bredspektret "
        "antibiotika og overført til intensivavdelingen.",
        "",
    ],
    [
        "The weather today is sunny with a high of 25 degrees. "
        "The stock market closed at an all-time high. "
        "Several new restaurants opened in the downtown area.",
        "",
    ],
]


def format_results(results):
    """Convert verification results to readable Markdown."""
    if not results:
        return "No results returned."

    error = results.get("summary", {}).get("error")
    if error:
        return f"**Error:** {error}"

    entities = results.get("verified_entities", [])
    if not entities:
        return "No medical entities found in the input text."

    summary = results.get("summary", {})
    meta = results.get("metadata", {})
    lang = results.get("language", "unknown")

    lines = []
    lines.append(f"**Language detected:** {lang}")
    lines.append(
        f"**Entities found:** {summary.get('total', 0)} | "
        f"Grounded: {summary.get('grounded', 0)} | "
        f"Partial: {summary.get('partial', 0)} | "
        f"Ungrounded: {summary.get('ungrounded', 0)} | "
        f"Average score: {summary.get('avg_score', 0)}"
    )

    if meta.get("icd10_using_fallback"):
        lines.append("*ICD-10: using embedded fallback (limited coverage)*")
    else:
        lines.append(f"*ICD-10: {meta.get('icd10_codes_loaded', 0)} codes loaded*")

    snomed_status = "available" if meta.get("snomed_api_available") else "using fallback"
    lines.append(f"*SNOMED-CT API: {snomed_status}*")
    lines.append("")
    lines.append("---")
    lines.append("")

    for i, entity in enumerate(entities, 1):
        conf = entity.get("confidence", {})
        status = conf.get("status", "Unknown")
        score = conf.get("score", 0)
        evidence = conf.get("evidence", {})

        # Status indicator
        if status == "Grounded":
            indicator = "GROUNDED"
        elif status == "Partial":
            indicator = "PARTIAL"
        else:
            indicator = "UNGROUNDED"

        lines.append(f"### Entity {i}: {entity.get('text_mention', '?')}")
        lines.append(f"**Type:** {entity.get('entity_type', '?')} | **Status:** {indicator} | **Score:** {score}")
        lines.append("")

        # ICD-10 details
        icd = entity.get("icd10", {})
        if icd.get("found"):
            match_note = f" ({icd.get('match_type', '')} match)" if icd.get("match_type") else ""
            lines.append(f"**ICD-10:** {icd.get('code', '?')}{match_note}")
            lines.append(f"  LLM said: {icd.get('llm_description', 'N/A')}")
            verified_desc = icd.get("verified_description", "")
            if verified_desc:
                lines.append(f"  Verified: {verified_desc}")
        else:
            lines.append(f"**ICD-10:** {icd.get('code', '?')} -- NOT FOUND in ontology")

        # SNOMED details
        sno = entity.get("snomed", {})
        if sno.get("found"):
            source_note = f" (source: {sno.get('source', '')})" if sno.get("source") else ""
            lines.append(f"**SNOMED-CT:** {sno.get('concept_id', '?')}{source_note}")
            lines.append(f"  LLM said: {sno.get('llm_term', 'N/A')}")
            verified_term = sno.get("verified_term", "")
            if verified_term:
                lines.append(f"  Verified: {verified_term}")
        else:
            lines.append(f"**SNOMED-CT:** {sno.get('concept_id', '?')} -- NOT FOUND")

        # Evidence summary
        lines.append(f"**Evidence:** ICD={evidence.get('icd10', '?')}, "
                      f"SNOMED={evidence.get('snomed', '?')}, "
                      f"Source={evidence.get('source_grounding', '?')}, "
                      f"LLM confidence={evidence.get('llm_confidence', '?')}")

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def run_verification(text, api_key):
    """Callback for the Gradio interface."""
    key = api_key.strip() if api_key else None
    if not key:
        key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return "Please provide an Anthropic API key (or set it as a Space secret)."

    if not text or not text.strip():
        return "Please enter clinical text to verify."

    results = verify_text(text.strip(), api_key=key)
    return format_results(results)


def build_app():
    with gr.Blocks(title="MedTermCheck") as app:
        gr.Markdown(
            "# MedTermCheck\n"
            "Verify medical entities extracted by LLMs against SNOMED-CT and ICD-10 ontologies.\n\n"
            "Paste clinical text below. The system will extract medical entities using Claude, "
            "then verify each entity against two independent ontology sources and assign a "
            "confidence score based on four verification signals."
        )

        with gr.Row():
            with gr.Column():
                text_input = gr.Textbox(
                    label="Clinical Text",
                    placeholder="Paste clinical text here...",
                    lines=6,
                )
                api_key_input = gr.Textbox(
                    label="Anthropic API Key (optional if set as Space secret)",
                    placeholder="sk-ant-...",
                    type="password",
                )
                submit_btn = gr.Button("Verify Entities", variant="primary")

            with gr.Column():
                output = gr.Markdown(label="Verification Results")

        gr.Examples(
            examples=EXAMPLES,
            inputs=[text_input, api_key_input],
            label="Example Inputs (click to load)",
        )

        gr.Markdown(
            "---\n"
            "**How scoring works:** Each entity is verified against ICD-10 (local lookup, weight 0.30), "
            "SNOMED-CT (API lookup, weight 0.30), source text grounding (fuzzy match, weight 0.20), "
            "and the LLM's own confidence (weight 0.10). A convergent evidence bonus (0.10) is added "
            "when all three verification sources agree.\n\n"
            "**Limitations:** This is a research demo, not a clinical tool. "
            "The evaluation set is small (20 annotated cases). "
            "Results depend on Claude API availability and SNOMED-CT API uptime. "
            "Norwegian text support is functional but less thoroughly tested than English.\n\n"
            "Built by Samuel Okoe-Mensah | "
            "[GitHub](https://github.com/SamInMotion) | "
            "[LinkedIn](https://www.linkedin.com/in/sammens/)"
        )

        submit_btn.click(
            fn=run_verification,
            inputs=[text_input, api_key_input],
            outputs=output,
        )

    return app


app = build_app()

if __name__ == "__main__":
    app.launch()
