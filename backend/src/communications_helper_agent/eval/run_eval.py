"""Run the meeting-to-issues prompt against the dataset and grade each output.

    uv run python -m communications_helper_agent.eval.run_eval
    uv run python -m communications_helper_agent.eval.run_eval --reps 3
    uv run python -m communications_helper_agent.eval.run_eval --variant v1

Everything runs on LM Studio, so a full pass costs nothing and can be re-run
freely. LM Studio must be up with the model loaded, or every case lands in
errors.jsonl as a harness error.

Grading is split. `graders.py` checks everything determinable in code (schema,
field ranges, excerpt grounding, assignee safety); the judge handles only what
needs fuzzy matching (did it find the real work, did it invent any).

Writes, under backend/.claude/hillclimb/meeting_to_issues/<variant>/:
    results.jsonl              one row per (case, rep) that produced output
    errors.jsonl               attempts that failed before producing any
    traces/<id>_rep<k>.json    full exchange, for auditing a surprising score

Attempts that never produced a scorable output go to errors.jsonl, never
results.jsonl -- a plumbing failure scored as 0 is indistinguishable from the
model genuinely doing badly, and would block resume from retrying it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from pathlib import Path

import lmstudio as lms

from .config import (
    CONTEXT_LENGTH,
    DATASET_DIR,
    FALLBACK_MODEL,
    JUDGE_MODEL,
    METRICS,
    PIPELINE_MODEL,
    RESULTS_ROOT,
    load_prompt,
    load_pipeline_prompt,
)
from .graders import grade_deterministic
from .judge_client import judge_call

# Only the fuzzy metrics -- the rest are graded by code in graders.py.
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "issue_recall": {"type": "number", "minimum": 0, "maximum": 1},
        "issue_precision": {"type": "number", "minimum": 0, "maximum": 1},
        "faithfulness": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning": {
            "type": "string",
            "description": (
                "For each score below 1.0, name the specific item or issue "
                "responsible."
            ),
        },
    },
    "required": ["issue_recall", "issue_precision", "faithfulness", "reasoning"],
    "additionalProperties": False,
}

JUDGE_METRICS = ("issue_recall", "issue_precision", "faithfulness")

# A local model on a long transcript is slow; this ceiling is generous but
# still reclaims the slot if generation hangs.
CASE_TIMEOUT_S = 600.0
MAX_ATTEMPTS = 3


def load_cases() -> list[dict]:
    cases = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(DATASET_DIR.glob("*.json"))
    ]
    if not cases:
        raise SystemExit(f"No cases in {DATASET_DIR}. Run generate_dataset.py first.")
    return cases


async def _with_backoff(coro_factory, what: str):
    """Retry transient failures with jittered backoff. Returns (result, retries).

    LM Studio is local, so the failures worth retrying are a busy server or a
    model still loading -- not rate limits.
    """
    for attempt in range(MAX_ATTEMPTS):
        try:
            return await coro_factory(), attempt
        except lms.LMStudioError as exc:
            if attempt == MAX_ATTEMPTS - 1:
                raise
            delay = (2**attempt) + random.uniform(0, 1)
            print(f"    {what}: {type(exc).__name__}, retrying in {delay:.1f}s")
            await asyncio.sleep(delay)
    raise RuntimeError("unreachable")


def _judge_sections() -> tuple[str, str]:
    """Split judge.md into its SYSTEM and USER halves."""
    text = load_prompt("judge.md")
    system = text.split("## SYSTEM", 1)[1].split("## USER")[0].strip()
    user = text.split("## USER", 1)[1].strip()
    return system, user


async def run_pipeline(transcript: str, model_key: str | None) -> tuple[str, str]:
    """Run the extraction prompt. Returns (raw_output, model_used).

    This mirrors what llm.service.ask() does, but against the async client.
    It does not call ask() directly because ask() is currently broken on main:
    get_model() became an async context manager, and ask() still treats its
    return value as a model handle. Once ask() is fixed to match, this should
    call it instead -- going through the app's own entry point is what keeps
    the eval honest.
    """
    key = model_key or FALLBACK_MODEL
    system = load_pipeline_prompt()

    async with lms.AsyncClient() as client:
        model = await client.llm.model(key, config={"contextLength": CONTEXT_LENGTH})
        chat = lms.Chat(system)
        chat.add_user_message(transcript)
        result = await model.respond(chat)

    return result.content, key


async def judge(case: dict, issues_json: str, model_key: str) -> tuple[dict, str]:
    """Grade the fuzzy half: recall, precision, faithfulness."""
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
        .replace("{issues}", issues_json)
    )

    (grade, used), _ = await _with_backoff(
        lambda: judge_call(model_key, system, user, JUDGE_SCHEMA, CONTEXT_LENGTH),
        "judge",
    )
    return grade, used


async def run_case(
    case: dict,
    rep: int,
    model_key: str | None,
    out_dir: Path,
    sem: asyncio.Semaphore,
) -> tuple[dict | None, dict | None]:
    """Run and grade one (case, rep). Returns (result_row, error_row)."""
    case_id = case["id"]
    transcript = case["data"]

    async with sem:
        started = time.monotonic()
        try:
            (raw, model_used), retries = await asyncio.wait_for(
                _with_backoff(
                    lambda: run_pipeline(transcript, model_key), "pipeline"
                ),
                timeout=CASE_TIMEOUT_S,
            )
            latency = time.monotonic() - started

            # Code-graded half. Runs even on unparseable output, so a
            # correct-but-malformed answer loses schema points rather than
            # vanishing.
            det = grade_deterministic(raw, transcript)

            # The judge sees the parsed issues when available, else the raw
            # text -- it still has to decide whether the right work was found.
            issues_for_judge = (
                json.dumps(det["issues"], indent=2)
                if det["issues"] is not None
                else raw
            )
            fuzzy, judge_used = await judge(case, issues_for_judge, JUDGE_MODEL)

            grade = {**det["scores"], **{m: fuzzy[m] for m in JUDGE_METRICS}}

            (out_dir / "traces").mkdir(parents=True, exist_ok=True)
            trace = [
                {"role": "system", "content": load_pipeline_prompt()},
                {"role": "user", "content": transcript},
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        "[CODE GRADER]\n"
                        + json.dumps(
                            {
                                "scores": det["scores"],
                                "problems": det["problems"],
                                "parse_error": det["parse_error"],
                            },
                            indent=2,
                        )
                        + "\n\n[JUDGE] criteria:\n"
                        + json.dumps(case["solution_criteria"], indent=2)
                    ),
                },
                {"role": "assistant", "content": json.dumps(fuzzy, indent=2)},
            ]
            (out_dir / "traces" / f"{case_id}_rep{rep}.json").write_text(
                json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            row = {
                "prompt_id": case_id,
                "rep": rep,
                "prompt": transcript,
                "tags": [case.get("difficulty", "unknown")],
                "status": "ok",
                "grade": {m["id"]: grade[m["id"]] for m in METRICS},
                "explanation": {m: fuzzy["reasoning"] for m in JUDGE_METRICS},
                "model": model_used,
                "judge_model": judge_used,
                "latency_s": round(latency, 2),
                "retries": retries,
                "n_issues": len(det["issues"]) if det["issues"] is not None else 0,
                "meta": {
                    "n_required_tasks": len(
                        case["solution_criteria"].get("required_tasks", [])
                    ),
                    "parse_error": det["parse_error"],
                    "grader_problems": det["problems"],
                    # Flag self-grading: the judge and the system under test
                    # sharing weights biases scores upward.
                    "judge_is_pipeline_model": judge_used == model_used,
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
            spread = (max(vals) - min(vals)) / 2 if len(vals) > 1 else 0.0
            print(f"  {m['label']:<10} {mean:.3f}  (spread +/-{spread:.3f})")

    by_tag: dict[str, list[float]] = {}
    for r in ok:
        by_tag.setdefault(r["tags"][0], []).append(r["grade"][METRICS[0]["id"]])
    print(f"\n{METRICS[0]['label']} by difficulty:")
    for tag, vals in sorted(by_tag.items()):
        print(f"  {tag:<8} {sum(vals) / len(vals):.3f}  (n={len(vals)})")

    parse_fails = sum(1 for r in ok if r["meta"].get("parse_error"))
    if parse_fails:
        print(f"\n{parse_fails}/{len(ok)} output(s) did not parse as JSON.")

    if any(r["meta"].get("judge_is_pipeline_model") for r in ok):
        print(
            "\nNote: the judge ran on the same model as the pipeline, which "
            "biases scores upward.\nSet $JUDGE_MODEL to a different local "
            "model if you have one loaded."
        )


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
                    {"id": "n_issues", "label": "Issues"},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"pipeline={args.model or '(client default)'}  judge={JUDGE_MODEL}\n"
        f"{len(todo)} run(s) at concurrency {args.concurrency}\n"
    )

    # LM Studio serves one model at a time; too much concurrency just queues.
    sem = asyncio.Semaphore(args.concurrency)
    tasks = [run_case(c, r, args.model, out_dir, sem) for c, r in todo]

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
            print(
                f"  [{err['prompt_id']} rep{err['rep']}] "
                f"{err['failure_class']}: {err['detail'][:80]}"
            )

    print(f"\n{n_ok} scored, {n_err} failed -> {out_dir}")
    if n_err and not n_ok:
        print("Every case failed. Is LM Studio running with the model loaded?")
    if n_ok:
        _summarize(results_path)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the meeting-to-issues eval.")
    ap.add_argument("--variant", default="baseline", help="baseline, v1, v2, ...")
    ap.add_argument(
        "--model",
        default=PIPELINE_MODEL,
        help="LM Studio model key (default: $LM_MODEL, else the client default)",
    )
    ap.add_argument("--reps", type=int, default=2, help="repetitions per case")
    ap.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="in-flight cases; LM Studio serves one model, so keep this low",
    )
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
