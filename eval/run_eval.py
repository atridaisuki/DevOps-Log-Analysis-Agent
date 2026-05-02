"""Evaluation script — runs the agent against each case in dataset.json
and scores root-cause accuracy, affected-service recall, step count, and latency.

Usage:
    python -m eval.run_eval                  # run all cases
    python -m eval.run_eval --ids eval_01_db_pool_basic eval_02_oom_basic
    python -m eval.run_eval --dry-run        # print cases without running
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

EVAL_DIR = Path(__file__).parent
DATASET_PATH = EVAL_DIR / "dataset.json"
RESULTS_PATH = EVAL_DIR / "results.json"

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


# ── scoring helpers ──────────────────────────────────────────────────

def score_root_cause(report_text: str, keywords: list[str]) -> float:
    """Return fraction of expected keywords found in the report (case-insensitive)."""
    text_lower = report_text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    return round(hits / len(keywords), 2) if keywords else 0.0


def score_services(report_text: str, expected: list[str]) -> float:
    """Return fraction of expected affected services mentioned in the report."""
    text_lower = report_text.lower()
    hits = sum(1 for svc in expected if svc.lower() in text_lower)
    return round(hits / len(expected), 2) if expected else 0.0


# ── run one case ─────────────────────────────────────────────────────

def run_case(case: dict, base_url: str) -> dict:
    """Run a single eval case against the /agent/analyze endpoint."""
    payload = {
        "goal": case["goal"],
        "scenario": case["scenario"],
        "max_iterations": case.get("max_iterations", 10),
        "auto_approve": True,
    }

    start = time.perf_counter()
    try:
        resp = httpx.post(
            f"{base_url}/agent/analyze",
            json=payload,
            timeout=300.0,  # agent can take a while
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return {
            "id": case["id"],
            "status": "error",
            "error": str(exc),
            "root_cause_score": 0.0,
            "service_score": 0.0,
            "iterations": 0,
            "tool_calls": 0,
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        }

    elapsed = round((time.perf_counter() - start) * 1000, 2)

    report = data.get("root_cause", "")
    rc_score = score_root_cause(report, case["expected_root_cause_keywords"])
    svc_score = score_services(report, case["expected_affected_services"])

    return {
        "id": case["id"],
        "status": data.get("status", "unknown"),
        "root_cause_score": rc_score,
        "service_score": svc_score,
        "iterations": data.get("iterations", 0),
        "tool_calls": len(data.get("tool_trace", [])),
        "duration_ms": elapsed,
        "report_preview": report[:300],
    }


# ── main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run DevOps Agent evaluation")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--ids", nargs="*", help="Only run these case IDs")
    parser.add_argument("--dry-run", action="store_true", help="Print cases, don't run")
    args = parser.parse_args()

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

    if args.ids:
        dataset = [c for c in dataset if c["id"] in args.ids]

    if not dataset:
        print("No matching cases found.")
        sys.exit(1)

    if args.dry_run:
        for c in dataset:
            print(f"  {c['id']:30s}  {c['scenario']:25s}  {c['difficulty']}")
        print(f"\nTotal: {len(dataset)} cases")
        return

    print(f"Running {len(dataset)} eval cases against {args.base_url}\n")

    results = []
    for i, case in enumerate(dataset, 1):
        print(f"[{i}/{len(dataset)}] {case['id']} ...", end=" ", flush=True)
        result = run_case(case, args.base_url)
        results.append(result)

        status_icon = "OK" if result["root_cause_score"] >= 0.3 else "MISS"
        print(
            f"{status_icon}  rc={result['root_cause_score']:.0%}  "
            f"svc={result['service_score']:.0%}  "
            f"steps={result['iterations']}  "
            f"tools={result['tool_calls']}  "
            f"{result['duration_ms']:.0f}ms"
        )

    # ── aggregate stats ──────────────────────────────────────────────
    valid = [r for r in results if r["status"] != "error"]
    n = len(valid)

    if n > 0:
        avg_rc = sum(r["root_cause_score"] for r in valid) / n
        avg_svc = sum(r["service_score"] for r in valid) / n
        avg_steps = sum(r["iterations"] for r in valid) / n
        avg_tools = sum(r["tool_calls"] for r in valid) / n
        avg_dur = sum(r["duration_ms"] for r in valid) / n
        pass_rate = sum(1 for r in valid if r["root_cause_score"] >= 0.3) / n
    else:
        avg_rc = avg_svc = avg_steps = avg_tools = avg_dur = pass_rate = 0.0

    summary = {
        "total_cases": len(dataset),
        "completed": n,
        "errors": len(results) - n,
        "pass_rate": round(pass_rate, 2),
        "avg_root_cause_score": round(avg_rc, 2),
        "avg_service_score": round(avg_svc, 2),
        "avg_iterations": round(avg_steps, 1),
        "avg_tool_calls": round(avg_tools, 1),
        "avg_duration_ms": round(avg_dur, 1),
    }

    output = {"summary": summary, "results": results}
    RESULTS_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"  Pass rate:        {pass_rate:.0%} ({sum(1 for r in valid if r['root_cause_score'] >= 0.3)}/{n})")
    print(f"  Avg RC score:     {avg_rc:.0%}")
    print(f"  Avg SVC score:    {avg_svc:.0%}")
    print(f"  Avg iterations:   {avg_steps:.1f}")
    print(f"  Avg tool calls:   {avg_tools:.1f}")
    print(f"  Avg duration:     {avg_dur:.0f}ms")
    print(f"{'='*60}")
    print(f"\nResults saved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
