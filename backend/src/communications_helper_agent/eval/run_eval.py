"""Run the summarization prompt against the dataset and grade each output.

    uv run python -m communications_helper_agent.eval.run_eval
    uv run python -m communications_helper_agent.eval.run_eval --reps 3
    uv run python -m communications_helper_agent.eval.run_eval --variant v1

Writes, under backend/.claude/hillclimb/summarize/<variant>/:
    results.jsonl              one row per (case, rep) that produced a summary
    errors.jsonl               attempts that failed before producing one
    traces/<id>_rep<k>.json    full exchange, for auditing a surprising score

Attempts that never produced a scorable output go to errors.jsonl, never
results.jsonl -- a plumbing failure scored as 0 would be indistinguishable from
the model genuinely doing badly, and would block resume from retrying it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from pathlib import Path
from typing import Any

from anthropic import (
    APIConnectionError,
    APIStatusError,
    AsyncAnthropic,
    RateLimitError,
)

from .config import (
    DATASET_DIR,
    JUDGE_MODEL,
    METRICS,
    RESULTS_ROOT,
    SUMMARIZER_MODEL,
    load_prompt,
    load_summarize_prompt,
)

# Independent 0-1 scores. Kept separate rather than blended: a drop in recall
# (dropped tasks) and a drop in precision (invented tasks) have different fixes.
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "task_recall": {"type": "number", "minimum": 0, "maximum": 1},
        "task_precision": {"type": "number", "minimum": 0, "maximum": 1},
        "faithfulness": {"type": "number", "minimum": 0, "maximum": 1},
        "coverage": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning": {
            "type": "string",
            "description": (
                "For each score below 1.0, name the specific task or claim "
                "responsible."
            ),
        },
    },
    "required": [
        "task_recall",
        "task_precision",
        "faithfulness",
        "coverage",
        "reasoning",
    ],
    "additionalProperties": False,
}

CASE_TIMEOUT_S = 300.0  # hard per-case ceiling, independent of stream liveness
MAX_ATTEMPTS = 4


def load_cases() -> list[dict]:
    cases = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(DATASET_DIR.glob("*.json"))
    ]
    if not cases:
        raise SystemExit(f"No cases in {DATASET_DIR}. Run generate_dataset.py first.")
    return cases


def _assert_model(response: Any, requested: str) -> None:
    """A silently substituted model invalidates the comparison."""
    served = getattr(response, "model", None)
    if served and not served.startswith(requested.split("[")[0]):
        raise RuntimeError(f"served model {served!r} != requested {requested!r}")


async def _with_backoff(coro_factory, what: str) -> tuple[Any, int]:
    """Retry transient failures with jittered backoff. Returns (result, retries)."""
    for attempt in range(MAX_ATTEMPTS):
        try:
            return await coro_factory(), attempt
        except (RateLimitError, APIConnectionError) as exc:
            if attempt == MAX_ATTEMPTS - 1:
                raise
            delay = (2**attempt) + random.uniform(0, 1)
            print(f"    {what}: {type(exc).__name__}, retrying in {delay:.1f}s")
            await asyncio.sleep(delay)
        except APIStatusError as exc:
            if exc.status_code < 500 or attempt == MAX_ATTEMPTS - 1:
                raise
            await asyncio.sleep((2**attempt) + random.uniform(0, 1))
    raise RuntimeError("unreachable")


def _judge_sections() -> tuple[str, str]:
    """Split judge.md into its SYSTEM and USER halves."""
    text = load_prompt("judge.md")
    system = text.split("## SYSTEM", 1)[1].split("## USER")[0].strip()
    user = text.split("## USER", 1)[1].strip()
    return system, user


async def summarize(
    client: AsyncAnthropic, transcript: str, model: str
) -> tuple[str, Any, int]:
    """Run the prompt under test. Returns (summary, response, retries)."""
    prompt = load_summarize_prompt().replace("{transcript}", transcript)

    async def call():
        async with client.messages.stream(
            model=model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            return await stream.get_final_message()

    response, retries = await _with_backoff(call, "summarize")
    _assert_model(response, model)
    text = "".join(b.text for b in response.content if b.type == "text")
    return text, response, retries


async def judge(
    client: AsyncAnthropic, case: dict, summary: str, model: str
) -> tuple[dict, Any]:
    """Grade one summary against its criteria."""
    crit = case["solution_criteria"]
    system, body = _judge_sections()

    user = (
        body.replace(
            "{required_tasks}", json.dumps(crit.get("required_tasks", []), indent=2)
        )
        .replace("{must_mention}", json.dumps(crit.get("must_mention", []), indent=2))
        .replace(
            "{must_not_contain}",
            json.dumps(crit.get("must_not_contain", []), indent=2),
        )
        .replace("{summary}", summary)
    )

    async def call():
        return await client.messages.create(
            model=model,
            max_tokens=4000,
            system=system,
            output_config={
                "format": {
                    "type": "json_schema",
                    "name": "grade",
                    "schema": JUDGE_SCHEMA,
                }
            },
            messages=[{"role": "user", "content": user}],
        )

    response, _ = await _with_backoff(call, "judge")
    _assert_model(response, model)
    text = "".join(b.text for b in response.content if b.type == "text")
    return json.loads(text), response


async def run_case(
    client: AsyncAnthropic,
    case: dict,
    rep: int,
    model: str,
    out_dir: Path,
    sem: asyncio.Semaphore,
) -> tuple[dict | None, dict | None]:
    """Run and grade one (case, rep). Returns (result_row, error_row)."""
    case_id = case["id"]
    async with sem:
        started = time.monotonic()
        try:
            summary, resp, retries = await asyncio.wait_for(
                summarize(client, case["data"], model), timeout=CASE_TIMEOUT_S
            )
            latency = time.monotonic() - started

            if resp.stop_reason == "refusal":
                return None, {
                    "prompt_id": case_id,
                    "rep": rep,
                    "failure_class": "refusal",
                    "model": resp.model,
                    "usage": resp.usage.model_dump(),
                    "detail": str(getattr(resp, "stop_details", None)),
                }

            # A response clipped at max_tokens is not a wrong answer; mark it so
            # the report counts it separately rather than averaging it in.
            truncated = resp.stop_reason == "max_tokens"

            grade, judge_resp = await judge(client, case, summary, JUDGE_MODEL)

            (out_dir / "traces").mkdir(parents=True, exist_ok=True)
            trace = [
                {"role": "system", "content": load_summarize_prompt()},
                {"role": "user", "content": case["data"]},
                {"role": "assistant", "content": summary},
                {
                    "role": "user",
                    "content": (
                        "[JUDGE] criteria:\n"
                        + json.dumps(case["solution_criteria"], indent=2)
                    ),
                },
                {"role": "assistant", "content": json.dumps(grade, indent=2)},
            ]
            (out_dir / "traces" / f"{case_id}_rep{rep}.json").write_text(
                json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            row = {
                "prompt_id": case_id,
                "rep": rep,
                "prompt": case["data"],
                "tags": [case.get("difficulty", "unknown")],
                "stop_reason": resp.stop_reason,
                "status": "truncated" if truncated else "ok",
                "grade": {m["id"]: grade[m["id"]] for m in METRICS},
                "explanation": {m["id"]: grade["reasoning"] for m in METRICS},
                "model": resp.model,
                "usage": resp.usage.model_dump(),
                "judge_model": judge_resp.model,
                "judge_usage": judge_resp.usage.model_dump(),
                "latency_s": round(latency, 2),
                "retries": retries,
                "meta": {
                    "n_required_tasks": len(
                        case["solution_criteria"].get("required_tasks", [])
                    )
                },
            }
            return row, None

        except asyncio.TimeoutError:
            return None, {
                "prompt_id": case_id,
                "rep": rep,
                "failure_class": "timeout",
                "detail": f"exceeded {CASE_TIMEOUT_S}s",
            }
        except Exception as exc:  # noqa: BLE001 - any failure here is plumbing
            return None, {
                "prompt_id": case_id,
                "rep": rep,
                "failure_class": "harness_error",
                "detail": f"{type(exc).__name__}: {exc}",
            }


def _done_keys(path: Path) -> set[tuple[str, int]]:
    """(case, rep) pairs already written -- resume skips exactly these."""
    if not path.exists():
        return set()
    keys = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            keys.add((row["prompt_id"], row.get("rep", 0)))
    return keys


def _summarize(results_path: Path) -> None:
    """Print per-metric means over status-ok rows."""
    rows = [
        json.loads(line)
        for line in results_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ok = [r for r in rows if r.get("status") == "ok"]
    if not ok:
        return

    print(f"\nMeans over {len(ok)} scored rep(s):")
    for m in METRICS:
        vals = [r["grade"][m["id"]] for r in ok if m["id"] in r.get("grade", {})]
        if vals:
            mean = sum(vals) / len(vals)
            # Rough spread; treat differences smaller than this as noise.
            spread = (max(vals) - min(vals)) / 2 if len(vals) > 1 else 0.0
            print(f"  {m['label']:<10} {mean:.3f}  (spread +/-{spread:.3f})")

    by_tag: dict[str, list[float]] = {}
    for r in ok:
        by_tag.setdefault(r["tags"][0], []).append(r["grade"][METRICS[0]["id"]])
    print(f"\n{METRICS[0]['label']} by difficulty:")
    for tag, vals in sorted(by_tag.items()):
        print(f"  {tag:<8} {sum(vals) / len(vals):.3f}  (n={len(vals)})")


async def main_async(args) -> None:
    cases = load_cases()
    out_dir = RESULTS_ROOT / args.variant
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.jsonl"
    errors_path = out_dir / "errors.jsonl"

    done = _done_keys(results_path)
    todo = [
        (c, r) for c in cases for r in range(args.reps) if (c["id"], r) not in done
    ]
    if done:
        print(f"resuming: {len(done)} already done, {len(todo)} to run")
    if not todo:
        print("nothing to run")
        _summarize(results_path)
        return

    # _state.json tells the report builder what columns to draw.
    (RESULTS_ROOT / "_state.json").write_text(
        json.dumps(
            {
                "metrics": METRICS,
                "perf_fields": [
                    {"id": "latency_s", "label": "Latency", "unit": "s"},
                    {"id": "cost_usd", "label": "Cost", "unit": "$"},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    client = AsyncAnthropic()
    sem = asyncio.Semaphore(args.concurrency)
    tasks = [run_case(client, c, r, args.model, out_dir, sem) for c, r in todo]

    n_ok = n_err = 0
    for coro in asyncio.as_completed(tasks):
        row, err = await coro
        # Write as each case completes -- a crash mid-run shouldn't cost the
        # cases that already finished.
        if row:
            with results_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n_ok += 1
            scores = " ".join(f"{k}={v:.2f}" for k, v in row["grade"].items())
            print(f"  [{row['prompt_id']} rep{row['rep']}] {scores}")
        if err:
            with errors_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(err, ensure_ascii=False) + "\n")
            n_err += 1
            print(f"  [{err['prompt_id']} rep{err['rep']}] {err['failure_class']}")

    print(f"\n{n_ok} scored, {n_err} failed -> {out_dir}")
    if n_ok:
        _summarize(results_path)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the summarization eval.")
    ap.add_argument("--variant", default="baseline", help="baseline, v1, v2, ...")
    ap.add_argument("--model", default=SUMMARIZER_MODEL)
    ap.add_argument("--reps", type=int, default=2, help="repetitions per case")
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
