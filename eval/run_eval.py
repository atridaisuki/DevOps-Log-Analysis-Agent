"""Evaluation script — runs the agent against each case in dataset.json
and scores root-cause accuracy, affected-service recall, step count, and latency.

Usage:
    python -m eval.run_eval                  # run all cases
    python -m eval.run_eval --ids eval_01_db_pool_basic eval_02_oom_basic
    python -m eval.run_eval --dry-run        # print cases without running
    python -m eval.run_eval --no-judge       # skip LLM-as-Judge (keyword only)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

EVAL_DIR = Path(__file__).parent
DATASET_PATH = EVAL_DIR / "dataset.json"
RESULTS_PATH = EVAL_DIR / "results.json"

DEFAULT_BASE_URL = "http://127.0.0.1:8000"

JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "deepseek-v4-pro")
JUDGE_API_KEY = os.environ.get("JUDGE_API_KEY", "")


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


# ── LLM-as-Judge ────────────────────────────────────────────────────

_JUDGE_PROMPT = """\
You are evaluating an incident analysis report produced by an AI agent.

## Case Description
User's question: {goal}
Expected root cause: {expected_root_cause}
Expected affected services: {expected_services}

## Agent's Report
{report}

## Scoring Criteria
Score the report from 0 to 10:
- 9-10: Correctly identifies the root cause with clear evidence chain and actionable suggestions
- 7-8: Correctly identifies the root cause but evidence or suggestions are incomplete
- 5-6: Partially correct — mentions the right area but misses the specific mechanism
- 3-4: Vaguely related but misses the key issue
- 0-2: Completely wrong or irrelevant

## Response Format
Respond with ONLY a JSON object (no markdown, no extra text):
{{"score": <int 0-10>, "correct": <bool>, "reasoning": "<one sentence explanation>"}}
"""


def llm_judge_root_cause(
    report: str,
    case: dict,
    api_key: str,
    base_url: str = "",
) -> dict:
    """Use LLM to semantically evaluate if the report identifies the root cause.

    Uses Anthropic SDK (compatible with DeepSeek via base_url).

    Returns {"score": int, "correct": bool, "reasoning": str} or
    {"score": -1, "correct": False, "reasoning": "error message"} on failure.
    """
    from anthropic import Anthropic

    prompt = _JUDGE_PROMPT.format(
        goal=case["goal"],
        expected_root_cause=case.get("expected_root_cause", ", ".join(case["expected_root_cause_keywords"])),
        expected_services=", ".join(case["expected_affected_services"]),
        report=report[:3000],
    )

    try:
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = Anthropic(**client_kwargs)

        response = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        # Extract text from content blocks, handling ThinkingBlock and TextBlock
        text_parts = []
        thinking_parts = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
            elif hasattr(block, "thinking"):
                thinking_parts.append(block.thinking)
        text = "".join(text_parts).strip()
        # Fallback: if text blocks are empty, try to extract JSON from thinking
        if not text and thinking_parts:
            thinking_text = "".join(thinking_parts)
            # Try to find JSON in thinking output
            import re
            json_match = re.search(r'\{[^{}]*"score"[^{}]*\}', thinking_text)
            if json_match:
                text = json_match.group(0)
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json.loads(text)
        result.setdefault("score", 0)
        result.setdefault("correct", False)
        result.setdefault("reasoning", "")
        return result
    except Exception as exc:
        return {"score": -1, "correct": False, "reasoning": f"Judge error: {str(exc)[:100]}"}


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
            timeout=600.0,
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

    token_usage = data.get("token_usage") or {}

    return {
        "id": case["id"],
        "status": data.get("status", "unknown"),
        "root_cause_score": rc_score,
        "service_score": svc_score,
        "iterations": data.get("iterations", 0),
        "tool_calls": len(data.get("tool_trace", [])),
        "duration_ms": elapsed,
        "total_input_tokens": token_usage.get("total_input", 0),
        "total_output_tokens": token_usage.get("total_output", 0),
        "total_cost_usd": token_usage.get("total_cost_usd", 0.0),
        "report_preview": report[:300],
        "report_full": report,
    }


# ── main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run DevOps Agent evaluation")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--ids", nargs="*", help="Only run these case IDs")
    parser.add_argument("--dry-run", action="store_true", help="Print cases, don't run")
    parser.add_argument("--no-judge", action="store_true", help="Skip LLM-as-Judge scoring")
    parser.add_argument("--judge-only", action="store_true", help="Re-run judge on previous results (no agent calls)")
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

    # ── Judge-only mode: re-score previous results without re-running agent ──
    if args.judge_only:
        judge_key = JUDGE_API_KEY or os.environ.get("ANTHROPIC_API_KEY", "")
        judge_base = os.environ.get("ANTHROPIC_BASE_URL", "")
        if not judge_key:
            print("ERROR: JUDGE_API_KEY / ANTHROPIC_API_KEY not set")
            sys.exit(1)

        if not RESULTS_PATH.exists():
            print("ERROR: No previous results found. Run eval first.")
            sys.exit(1)

        prev = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        results = prev["results"]
        case_map = {c["id"]: c for c in dataset}

        # Filter by --ids if specified
        if args.ids:
            results = [r for r in results if r["id"] in args.ids]

        print(f"Re-running LLM-as-Judge ({JUDGE_MODEL}) on {len(results)} results...\n")

        for result in results:
            if result.get("status") == "error":
                result["judge_score"] = -1
                result["judge_correct"] = False
                result["judge_reasoning"] = "skipped (agent error)"
                continue

            case = case_map.get(result["id"])
            if not case:
                continue

            report = result.get("report_full", result.get("report_preview", ""))
            judge_result = llm_judge_root_cause(report, case, judge_key, judge_base)
            result["judge_score"] = judge_result["score"]
            result["judge_correct"] = judge_result["correct"]
            result["judge_reasoning"] = judge_result["reasoning"]

            icon = "Y" if judge_result["correct"] else "N"
            print(f"  [{icon}] {result['id']:30s}  score={judge_result['score']}/10  {judge_result['reasoning'][:60]}")

        # Update results file
        judged = [r for r in results if r.get("judge_score", -1) >= 0]
        if judged:
            prev["summary"]["llm_judge_avg_score"] = round(sum(r["judge_score"] for r in judged) / len(judged), 1)
            prev["summary"]["llm_judge_correct_rate"] = round(sum(1 for r in judged if r["judge_correct"]) / len(judged), 2)

        RESULTS_PATH.write_text(json.dumps(prev, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nJudge avg: {prev['summary'].get('llm_judge_avg_score', 'N/A')}/10")
        print(f"Judge pass: {prev['summary'].get('llm_judge_correct_rate', 'N/A'):.0%}")
        print(f"Results updated: {RESULTS_PATH}")
        return

    # Check if LLM judge is available
    use_judge = not args.no_judge
    judge_key = JUDGE_API_KEY or os.environ.get("ANTHROPIC_API_KEY", "")
    judge_base = os.environ.get("ANTHROPIC_BASE_URL", "")
    if use_judge and not judge_key:
        print("WARN: JUDGE_API_KEY / ANTHROPIC_API_KEY not set, disabling LLM-as-Judge\n")
        use_judge = False

    print(f"Running {len(dataset)} eval cases against {args.base_url}")
    print(f"LLM-as-Judge: {'ON (' + JUDGE_MODEL + ')' if use_judge else 'OFF'}\n")

    results = []
    case_map = {c["id"]: c for c in dataset}

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

    # ── LLM-as-Judge pass ────────────────────────────────────────────
    if use_judge:
        print(f"\nRunning LLM-as-Judge ({JUDGE_MODEL}) ...")
        for result in results:
            if result["status"] == "error":
                result["judge_score"] = -1
                result["judge_correct"] = False
                result["judge_reasoning"] = "skipped (agent error)"
                continue

            case = case_map[result["id"]]
            report = result.get("report_full", result.get("report_preview", ""))
            judge_result = llm_judge_root_cause(report, case, judge_key, judge_base)
            result["judge_score"] = judge_result["score"]
            result["judge_correct"] = judge_result["correct"]
            result["judge_reasoning"] = judge_result["reasoning"]

            icon = "Y" if judge_result["correct"] else "N"
            print(f"  [{icon}] {result['id']:30s}  score={judge_result['score']}/10  {judge_result['reasoning'][:60]}")

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
        avg_input = sum(r.get("total_input_tokens", 0) for r in valid) / n
        avg_output = sum(r.get("total_output_tokens", 0) for r in valid) / n
        avg_cost = sum(r.get("total_cost_usd", 0.0) for r in valid) / n
    else:
        avg_rc = avg_svc = avg_steps = avg_tools = avg_dur = pass_rate = 0.0
        avg_input = avg_output = avg_cost = 0.0

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
        "avg_input_tokens": round(avg_input),
        "avg_output_tokens": round(avg_output),
        "avg_cost_usd": round(avg_cost, 4),
    }

    if use_judge:
        judged = [r for r in valid if r.get("judge_score", -1) >= 0]
        if judged:
            summary["llm_judge_avg_score"] = round(sum(r["judge_score"] for r in judged) / len(judged), 1)
            summary["llm_judge_correct_rate"] = round(sum(1 for r in judged if r["judge_correct"]) / len(judged), 2)

    # Strip full report from saved results to keep file manageable
    for r in results:
        r.pop("report_full", None)

    output = {"summary": summary, "results": results}
    RESULTS_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"  Pass rate:        {pass_rate:.0%} ({sum(1 for r in valid if r['root_cause_score'] >= 0.3)}/{n})")
    print(f"  Avg RC score:     {avg_rc:.0%} (keyword)")
    if use_judge and "llm_judge_avg_score" in summary:
        print(f"  LLM Judge score:  {summary['llm_judge_avg_score']}/10")
        print(f"  LLM Judge pass:   {summary['llm_judge_correct_rate']:.0%}")
    print(f"  Avg SVC score:    {avg_svc:.0%}")
    print(f"  Avg iterations:   {avg_steps:.1f}")
    print(f"  Avg tool calls:   {avg_tools:.1f}")
    print(f"  Avg duration:     {avg_dur:.0f}ms")
    print(f"  Avg tokens:       {avg_input:.0f} input / {avg_output:.0f} output")
    print(f"  Avg cost:         ${avg_cost:.4f}")
    print(f"{'='*60}")
    print(f"\nResults saved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
