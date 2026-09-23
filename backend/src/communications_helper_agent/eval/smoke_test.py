"""Check the harness works before running anything that takes real time.

    uv run python -m communications_helper_agent.eval.smoke_test

Six checks, cheapest first, each isolating one layer. They stop at the first
failure, so what breaks tells you where the problem is instead of leaving you
to guess from a run that produced nothing.

    1. imports            modules load, no missing dependency
    2. prompt             MEETING_TO_ISSUES_PROMPT is readable off disk
    3. graders            deterministic checks score known input correctly
    4. lm studio          the server is up and the model answers
    5. structured output  response_format returns schema-valid JSON
    6. end to end         one tiny transcript through pipeline + graders + judge

Checks 1-3 need nothing running. Checks 4-6 need LM Studio up with the model
loaded. Nothing here writes to the dataset or the results directory.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

MINI_TRANSCRIPT = """\
Priya: alright, quick sync. How did the deploy go last night?
Sam: fine, but the search is really slow when you change filters.
Priya: how slow?
Sam: couple of seconds. It got worse after the index change.
Ana: I can take the migration script for the user table, probably Thursday.
Sam: should we add a Redis cache for the session lookups?
Priya: let's not, not this sprint. Too much to land at once.
Sam: fair.
Priya: anything else? No? Good, short one today."""

# What a correct extraction finds: the slow search, and Ana's migration script.
# The Redis cache was explicitly rejected -- proposing it is a failure.
MINI_CASE = {
    "id": "_smoke",
    "difficulty": "clean",
    "data": MINI_TRANSCRIPT,
    "solution_criteria": {
        "required_tasks": [
            {
                "task": "Fix slow search when filters change",
                "owner": None,
                "evidence": "Sam: fine, but the search is really slow when you change filters.",
            },
            {
                "task": "Write the migration script for the user table",
                "owner": "Ana",
                "evidence": "Ana: I can take the migration script for the user table, probably Thursday.",
            },
        ],
        "must_mention": ["The team decided not to add a Redis cache this sprint"],
        "must_not_contain": ["Add a Redis cache for session lookups"],
    },
}


def _ok(label: str, detail: str = "") -> None:
    print(f"  PASS  {label}" + (f"  {detail}" if detail else ""))


def _fail(label: str, detail: str, fix: str) -> None:
    print(f"  FAIL  {label}")
    print(f"        {detail}")
    print(f"        fix: {fix}")


def check_imports() -> bool:
    try:
        from . import config, graders, judge_client, run_eval  # noqa: F401

        _ok("imports", "all eval modules load")
        return True
    except Exception as exc:  # noqa: BLE001
        _fail(
            "imports",
            f"{type(exc).__name__}: {exc}",
            "run `uv sync` from backend/",
        )
        return False


def check_prompt() -> bool:
    from .config import load_pipeline_prompt

    try:
        prompt = load_pipeline_prompt()
    except Exception as exc:  # noqa: BLE001
        _fail(
            "prompt",
            f"could not read MEETING_TO_ISSUES_PROMPT: {exc}",
            "check llm/system_prompts.py still defines it",
        )
        return False

    if len(prompt) < 500:
        _fail(
            "prompt",
            f"suspiciously short ({len(prompt)} chars)",
            "check llm/system_prompts.py",
        )
        return False

    _ok("prompt", f"{len(prompt)} chars from llm/system_prompts.py")
    return True


def check_graders() -> bool:
    """Score a known-good and a known-bad issue list.

    If the graders can't tell those apart, every metric downstream is noise.
    """
    from .graders import grade_deterministic

    good = json.dumps(
        [
            {
                "title": "Fix slow search on filter change",
                "description": "Search takes seconds after the index change.",
                "type": "bug",
                "tags": ["performance"],
                "priority": 4,
                "assignee": None,
                "assignee_confidence": None,
                "suggested_repo": None,
                "source_excerpt": "the search is really slow when you change filters.",
                "status": "proposed",
            }
        ]
    )
    res = grade_deterministic(good, MINI_TRANSCRIPT)
    if res["scores"] != {
        "schema_valid": 1.0,
        "fields_valid": 1.0,
        "excerpt_grounded": 1.0,
        "assignee_safe": 1.0,
    }:
        _fail(
            "graders",
            f"clean input did not score 1.0: {res['scores']} {res['problems']}",
            "graders.py regression -- a correct list must score perfectly",
        )
        return False

    bad = json.dumps(
        [
            {
                "title": "Add Redis cache",
                "description": "d",
                "type": "enhancement",  # not in the enum
                "tags": [],
                "priority": 9,  # out of range
                "assignee": "Marcus",  # never spoke
                "assignee_confidence": "high",
                "suggested_repo": None,
                "source_excerpt": "We agreed to add a Redis cache.",  # never said
                "status": "open",  # must be "proposed"
            }
        ]
    )
    res = grade_deterministic(bad, MINI_TRANSCRIPT)
    if res["scores"]["excerpt_grounded"] != 0.0:
        _fail(
            "graders",
            "a fabricated source_excerpt scored as grounded",
            "excerpt_grounded is the anti-fabrication check -- it must catch this",
        )
        return False
    if res["scores"]["assignee_safe"] != 0.0 or res["scores"]["fields_valid"] == 1.0:
        _fail(
            "graders",
            f"bad input scored too well: {res['scores']}",
            "graders.py regression",
        )
        return False

    _ok("graders", "clean scores 1.0, fabricated excerpt + bad fields caught")
    return True


async def check_lmstudio() -> bool:
    import lmstudio as lms

    from .config import CONTEXT_LENGTH, FALLBACK_MODEL, PIPELINE_MODEL

    key = PIPELINE_MODEL or FALLBACK_MODEL
    try:
        started = time.monotonic()
        async with lms.AsyncClient() as client:
            model = await client.llm.model(
                key, config={"contextLength": CONTEXT_LENGTH}
            )
            result = await model.respond("Reply with exactly: ok")
        elapsed = time.monotonic() - started
    except Exception as exc:  # noqa: BLE001
        _fail(
            "lm studio",
            f"{type(exc).__name__}: {str(exc)[:160]}",
            f"start LM Studio, load {key!r}, and enable the local server "
            "(Developer tab -> Status: Running)",
        )
        return False

    _ok("lm studio", f"{key} responded in {elapsed:.1f}s")
    return True


async def check_structured_output() -> bool:
    """The judge depends on schema-constrained JSON. Verify it round-trips."""
    from .config import CONTEXT_LENGTH, JUDGE_MODEL
    from .judge_client import judge_call

    schema = {
        "type": "object",
        "properties": {
            "score": {"type": "number", "minimum": 0, "maximum": 1},
            "reasoning": {"type": "string"},
        },
        "required": ["score", "reasoning"],
        "additionalProperties": False,
    }
    try:
        grade, used = await judge_call(
            JUDGE_MODEL,
            "You return JSON matching the schema. Nothing else.",
            "Return score 0.5 and a one-sentence reasoning.",
            schema,
            CONTEXT_LENGTH,
        )
    except Exception as exc:  # noqa: BLE001
        _fail(
            "structured output",
            f"{type(exc).__name__}: {str(exc)[:200]}",
            "the judge model may not support response_format json_schema -- "
            "try a different $JUDGE_MODEL",
        )
        return False

    if not isinstance(grade.get("score"), (int, float)):
        _fail(
            "structured output",
            f"score came back as {type(grade.get('score')).__name__}: {grade}",
            "model ignored the schema -- try a different $JUDGE_MODEL",
        )
        return False

    _ok("structured output", f"{used} returned schema-valid JSON")
    return True


async def check_end_to_end() -> bool:
    """One short transcript through the whole path, without touching results/."""
    from .graders import grade_deterministic
    from .run_eval import JUDGE_METRICS, judge, run_pipeline
    from .config import JUDGE_MODEL

    print("\n  running one case end to end (this takes a minute)...")

    try:
        started = time.monotonic()
        raw, model_used = await run_pipeline(MINI_TRANSCRIPT, None)
        pipeline_s = time.monotonic() - started
    except Exception as exc:  # noqa: BLE001
        _fail("end to end", f"pipeline failed: {exc}", "see the lm studio check")
        return False

    det = grade_deterministic(raw, MINI_TRANSCRIPT)

    if det["parse_error"]:
        print(f"  WARN  pipeline output did not parse: {det['parse_error']}")
        print(f"        first 200 chars: {raw[:200]!r}")
        print(
            "        Not a harness bug -- the model under test produced "
            "unparseable output.\n"
            "        That is a real finding: it would score schema_valid 0.0."
        )

    issues_json = (
        json.dumps(det["issues"], indent=2) if det["issues"] is not None else raw
    )
    try:
        started = time.monotonic()
        fuzzy, judge_used = await judge(MINI_CASE, issues_json, JUDGE_MODEL)
        judge_s = time.monotonic() - started
    except Exception as exc:  # noqa: BLE001
        _fail("end to end", f"judge failed: {exc}", "see the structured output check")
        return False

    n = len(det["issues"]) if det["issues"] is not None else 0
    print()
    _ok("end to end", f"{model_used} -> {n} issue(s) in {pipeline_s:.0f}s")
    print(f"        judge ({judge_used}) graded in {judge_s:.0f}s")
    print(f"        code : {json.dumps(det['scores'])}")
    print(
        "        judge: "
        + json.dumps({m: fuzzy[m] for m in JUDGE_METRICS})
    )
    print(f"        judge said: {fuzzy['reasoning'][:200]}")

    if det["issues"]:
        print("\n        issues the model proposed:")
        for issue in det["issues"]:
            print(f"          - {issue.get('title')!r}")
        print(
            "\n        Expected: slow search, and Ana's migration script.\n"
            "        A Redis cache issue is WRONG -- the team rejected it."
        )

    if judge_used == model_used:
        print(
            "\n  NOTE  judge and pipeline are the same model, which inflates "
            "scores.\n        Set $JUDGE_MODEL to a second local model if you "
            "have one."
        )
    return True


async def main_async() -> int:
    print("Smoke-testing the eval harness\n")

    print("offline checks (nothing needs to be running):")
    for check in (check_imports, check_prompt, check_graders):
        if not check():
            print("\nStopped at the first failure. Fix it and re-run.")
            return 1

    print("\nlive checks (need LM Studio up with the model loaded):")
    for check in (check_lmstudio, check_structured_output, check_end_to_end):
        if not await check():
            print("\nStopped at the first failure. Fix it and re-run.")
            return 1

    print(
        "\nHarness works. Next: generate the dataset, read the cases, then "
        "check_judge."
    )
    return 0


def main() -> None:
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
