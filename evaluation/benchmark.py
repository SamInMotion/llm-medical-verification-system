"""
Benchmark runner for MedTermCheck.
Measures ICD-10 accuracy, entity recall, and hallucination detection
against the annotated test cases.

Usage:
    python -m evaluation.benchmark --api-key YOUR_KEY
    python -m evaluation.benchmark --api-key YOUR_KEY --cases tc01,tc02,tc03
"""

import json
import os
import sys
import argparse
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.verifier import verify_text


def load_test_cases(path="evaluation/test_cases.json", case_ids=None):
    with open(path, "r") as f:
        cases = json.load(f)
    if case_ids:
        cases = [c for c in cases if c["id"] in case_ids]
    return cases


def evaluate_case(case, api_key):
    """Run verification on a single test case and compare to expected."""
    text = case["text"]
    expected = case.get("expected_entities", [])

    results = verify_text(text, api_key=api_key)
    verified = results.get("verified_entities", [])

    evaluation = {
        "id": case["id"],
        "category": case["category"],
        "expected_count": len(expected),
        "extracted_count": len(verified),
        "icd_matches": 0,
        "icd_mismatches": 0,
        "entities_grounded": 0,
        "entities_partial": 0,
        "entities_ungrounded": 0,
    }

    # Count status distribution
    for v in verified:
        status = v.get("confidence", {}).get("status", "")
        if status == "Grounded":
            evaluation["entities_grounded"] += 1
        elif status == "Partial":
            evaluation["entities_partial"] += 1
        else:
            evaluation["entities_ungrounded"] += 1

    # Check ICD-10 accuracy against expected codes
    for exp in expected:
        exp_code = exp.get("icd10_code") or exp.get("correct_icd10", "")
        if not exp_code:
            continue

        matched = False
        for v in verified:
            extracted_code = v.get("icd10", {}).get("code", "")
            if extracted_code.upper() == exp_code.upper():
                matched = True
                break

        if matched:
            evaluation["icd_matches"] += 1
        else:
            evaluation["icd_mismatches"] += 1

    # Hallucination trap check: non-medical text should produce zero entities
    if case["category"] == "hallucination_trap":
        evaluation["hallucination_test"] = len(verified) == 0

    return evaluation


def run_benchmark(api_key, case_ids=None, verbose=True):
    cases = load_test_cases(case_ids=case_ids)
    if not cases:
        print("No test cases found.")
        return

    print(f"Running benchmark on {len(cases)} test cases...")
    print()

    results = []
    for i, case in enumerate(cases):
        if verbose:
            print(f"  [{i+1}/{len(cases)}] {case['id']} ({case['category']}): ", end="", flush=True)

        eval_result = evaluate_case(case, api_key)
        results.append(eval_result)

        if verbose:
            extracted = eval_result["extracted_count"]
            grounded = eval_result["entities_grounded"]
            print(f"{extracted} entities, {grounded} grounded")

        # Small delay between API calls
        time.sleep(1)

    print()
    print_summary(results)
    return results


def print_summary(results):
    total_cases = len(results)
    total_icd_matches = sum(r["icd_matches"] for r in results)
    total_icd_checks = sum(r["icd_matches"] + r["icd_mismatches"] for r in results)
    total_entities = sum(r["extracted_count"] for r in results)
    total_grounded = sum(r["entities_grounded"] for r in results)
    total_partial = sum(r["entities_partial"] for r in results)
    total_ungrounded = sum(r["entities_ungrounded"] for r in results)

    # Hallucination trap performance
    trap_cases = [r for r in results if "hallucination_test" in r]
    traps_passed = sum(1 for r in trap_cases if r["hallucination_test"])

    print("=" * 50)
    print("BENCHMARK RESULTS")
    print("=" * 50)
    print(f"Test cases run: {total_cases}")
    print(f"Total entities extracted: {total_entities}")
    print()

    if total_icd_checks > 0:
        icd_accuracy = total_icd_matches / total_icd_checks * 100
        print(f"ICD-10 accuracy: {total_icd_matches}/{total_icd_checks} ({icd_accuracy:.0f}%)")

    if total_entities > 0:
        print(f"Grounded: {total_grounded}/{total_entities} ({total_grounded/total_entities*100:.0f}%)")
        print(f"Partial: {total_partial}/{total_entities} ({total_partial/total_entities*100:.0f}%)")
        print(f"Ungrounded: {total_ungrounded}/{total_entities} ({total_ungrounded/total_entities*100:.0f}%)")

    if trap_cases:
        print(f"Hallucination traps passed: {traps_passed}/{len(trap_cases)}")

    print()

    # Per-category breakdown
    categories = set(r["category"] for r in results)
    for cat in sorted(categories):
        cat_results = [r for r in results if r["category"] == cat]
        cat_entities = sum(r["extracted_count"] for r in cat_results)
        cat_grounded = sum(r["entities_grounded"] for r in cat_results)
        print(f"  {cat}: {len(cat_results)} cases, {cat_entities} entities, {cat_grounded} grounded")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MedTermCheck benchmark")
    parser.add_argument("--api-key", required=True, help="Anthropic API key")
    parser.add_argument("--cases", default=None, help="Comma-separated case IDs to run")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-case output")
    args = parser.parse_args()

    case_ids = args.cases.split(",") if args.cases else None
    run_benchmark(args.api_key, case_ids=case_ids, verbose=not args.quiet)
