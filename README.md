
---
title: MedTermCheck
emoji: 🔬
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: "4.0.0"
app_file: app.py
pinned: false
---

# MedTermCheck

Verifies medical entities extracted by LLMs against clinical ontologies (SNOMED-CT and ICD-10). Checks whether extracted codes exist, whether descriptions match, and assigns a confidence score based on four independent verification signals.

## The Problem

LLMs regularly produce incorrect medical codes when extracting clinical information from text. A model might output "ICD-10: G31.9" for a patient with diabetes, which is actually a code for degenerative nervous system disease. Research shows ungrounded clinical LLM outputs have hallucination rates above 60%.

This tool catches those errors by checking each extracted entity against two independent ontology sources and the original text.

## Architecture

```
Clinical Text Input
       |
       v
Claude API Extraction
  (structured entity + code extraction)
       |
       v
Ontology Verification Layer
  |
  |-- ICD-10 Lookup (local CMS flat file, ~70K codes)
  |     - exact code match
  |     - parent code fallback
  |
  |-- SNOMED-CT Lookup (Snowstorm public API)
  |     - concept search by term
  |     - preferred term retrieval
  |
  |-- Source Text Grounding (rapidfuzz)
        - fuzzy match entity against input text
        - prevents false positive extractions
       |
       v
Confidence Scoring (4 signals)
       |
       v
Verification Report
```

## Confidence Scoring

Each entity receives a score between 0.0 and 1.0 based on four weighted signals:

| Signal | Weight | Why |
|--------|--------|-----|
| ICD-10 code match | 0.30 | Primary structured ontology. Exact match is strong evidence the code exists and is correctly assigned. |
| SNOMED-CT concept found | 0.30 | Independent second ontology. Confirms the medical concept exists in a different knowledge system. |
| Source text grounding | 0.20 | Checks that the entity actually appears in the input text. Catches cases where the LLM invents entities not present in the source. |
| LLM self-reported confidence | 0.10 | Weakest signal. The LLM is the system being audited, so its own confidence is the least trustworthy input. |
| Convergent bonus | 0.10 | Awarded when all three verification sources agree. Rewards convergent evidence. |

Status labels:
- **Grounded**: Both ICD-10 and SNOMED-CT confirm the entity
- **Partial**: One ontology confirms, or parent code match
- **Ungrounded**: Neither ontology confirms the extraction

## Setup

### Run locally

```bash
git clone https://github.com/SamInMotion/medtermcheck.git
cd medtermcheck
pip install -r requirements.txt
```

Download ICD-10 data (optional but recommended):
1. Go to https://www.cms.gov/medicare/coding-billing/icd-10-codes
2. Download "Code Descriptions in Tabular Order"
3. Place the text file in `data/icd10cm_codes.txt`

If the file is missing, the system uses a built-in fallback covering 20 common conditions.

Set your API key:
```bash
export ANTHROPIC_API_KEY=your-key-here
```

Run:
```bash
python app.py
```

### Run the benchmark

```bash
python -m evaluation.benchmark --api-key YOUR_KEY
```

## Project Structure

```
medtermcheck/
  app.py                  Gradio interface (HuggingFace Spaces entry point)
  requirements.txt        Python dependencies
  pipeline/
    extractor.py          Claude API medical entity extraction
    verifier.py           Pipeline orchestration
    confidence.py         4-signal evidence scoring
  ontology/
    icd_lookup.py         CMS ICD-10-CM parser with fallback
    snomed_client.py      Snowstorm API client with fallback
  evaluation/
    test_cases.json       20 annotated test cases
    benchmark.py          Accuracy measurement
  data/
    icd10cm_codes.txt     CMS flat file (download separately)
```

## Limitations

This is a research demo, not a clinical decision tool. The evaluation set is small (20 annotated cases). Results depend on Claude API availability and SNOMED-CT API uptime. Norwegian text support is functional but less tested than English. The confidence score reflects verification evidence, not diagnostic correctness.

## Background

Built by Samuel Okoe-Mensah. The ontology verification approach extends work from my MPhil thesis at the University of Bergen on ontology-enriched machine learning for medical text classification, where I found that structured knowledge from SNOMED-CT changed which features the classifier relied on, even when it did not improve overall accuracy.

- [Live Demo](https://huggingface.co/spaces/SamInMotion/medtermcheck)
- [LinkedIn](https://www.linkedin.com/in/sammens/)
- [GitHub](https://github.com/SamInMotion)
