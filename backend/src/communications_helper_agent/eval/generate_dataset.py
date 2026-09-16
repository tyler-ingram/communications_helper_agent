"""Generate the evaluation dataset.

Run once, offline. Writes one JSON file per case into eval/dataset/.
Cases are generated in small batches so each transcript gets real attention.

    uv run python -m communications_helper_agent.eval.generate_dataset
    uv run python -m communications_helper_agent.eval.generate_dataset --only edge

Generated cases are a STARTING POINT, not ground truth. Read every one before
trusting a score from it -- a mislabelled case scores a correct system wrong,
and that error is invisible once it's buried in an aggregate.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from anthropic import Anthropic

from .config import (
    DATASET_DIR,
    GENERATOR_MODEL,
    PROMPTS_DIR,
    DIFFICULTY_MIX,
    load_prompt,
)

# Split the generation prompt on its own SYSTEM/USER markers.
_SYSTEM_RE = re.compile(r"^## SYSTEM$(.*?)^## USER$", re.M | re.S)
_USER_RE = re.compile(r"^## USER$(.*)", re.M | re.S)


def _split_prompt(text: str) -> tuple[str, str]:
    sys_m, user_m = _SYSTEM_RE.search(text), _USER_RE.search(text)
    if not sys_m or not user_m:
        raise ValueError(
            f"{PROMPTS_DIR / 'dataset_generation.md'} must contain '## SYSTEM' "
            "and '## USER' section headers"
        )
    return sys_m.group(1).strip(), user_m.group(1).strip()


def _extract_json_array(text: str) -> list[dict]:
    """Pull the JSON array out of a model response.

    The prompt asks for bare JSON, but models sometimes wrap it in a fence.
    """
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S)
    raw = fenced.group(1) if fenced else text[text.index("[") : text.rindex("]") + 1]
    return json.loads(raw)


def _validate(case: dict, case_id: str) -> list[str]:
    """Structural checks. Catches malformed generations before they hit the eval.

    This does NOT check that labels are correct -- only a human reading the
    transcript can do that.
    """
    problems: list[str] = []
    crit = case.get("solution_criteria")
    if not isinstance(crit, dict):
        return [f"{case_id}: missing or malformed solution_criteria"]

    transcript = case.get("data", "")
    if not isinstance(transcript, str) or len(transcript.splitlines()) < 20:
        problems.append(f"{case_id}: transcript is missing or suspiciously short")

    # An unlabelled transcript is the whole point -- a recap at the end hands
    # the model the answer and the case stops measuring extraction.
    for leak in ("ACTION ITEM", "TODO:", "Action items:", "To summarize,"):
        if leak.lower() in transcript.lower():
            problems.append(f"{case_id}: transcript leaks the answer ({leak!r})")

    tasks = crit.get("required_tasks")
    if not isinstance(tasks, list):
        problems.append(f"{case_id}: required_tasks must be a list")
        return problems

    for i, task in enumerate(tasks):
        if not isinstance(task, dict) or not task.get("task"):
            problems.append(f"{case_id}: required_tasks[{i}] has no 'task'")
            continue
        # Evidence must be a real quote -- that is what makes a label auditable.
        ev = (task.get("evidence") or "").strip()
        if not ev:
            problems.append(f"{case_id}: required_tasks[{i}] has no evidence quote")
        elif ev not in transcript:
            problems.append(
                f"{case_id}: required_tasks[{i}] evidence not found verbatim "
                f"in transcript: {ev[:60]!r}"
            )

    if case.get("difficulty") == "edge" and tasks:
        problems.append(f"{case_id}: edge case must have zero required_tasks")
    if case.get("difficulty") != "edge":
        if not tasks:
            problems.append(f"{case_id}: non-edge case has no required_tasks")
        if not crit.get("must_not_contain"):
            problems.append(
                f"{case_id}: no must_not_contain -- nothing tests for hallucination"
            )
    return problems


def generate(difficulty: str, n: int, existing_ids: list[str]) -> list[dict]:
    client = Anthropic()
    system, user_tmpl = _split_prompt(load_prompt("dataset_generation.md"))
    user = (
        user_tmpl.replace("{n}", str(n))
        .replace("{difficulty}", difficulty)
        .replace("{existing_ids}", ", ".join(existing_ids) or "(none)")
    )

    # Streaming: transcripts are long, and a batch can run past the HTTP timeout.
    with client.beta.messages.stream(
        model=GENERATOR_MODEL,
        max_tokens=32000,
        system=system,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": user}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "refusal":
        raise RuntimeError(f"generation refused: {response.stop_details}")

    text = "".join(b.text for b in response.content if b.type == "text")
    return _extract_json_array(text)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate eval dataset cases.")
    ap.add_argument(
        "--only",
        choices=sorted(DIFFICULTY_MIX),
        help="generate just one difficulty tier",
    )
    ap.add_argument(
        "--batch", type=int, default=2, help="cases per API call (default 2)"
    )
    args = ap.parse_args()

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    existing = [p.stem for p in DATASET_DIR.glob("*.json")]
    plan = (
        {args.only: DIFFICULTY_MIX[args.only]} if args.only else dict(DIFFICULTY_MIX)
    )

    all_problems: list[str] = []
    for difficulty, target in plan.items():
        have = sum(
            1
            for p in DATASET_DIR.glob("*.json")
            if json.loads(p.read_text(encoding="utf-8")).get("difficulty") == difficulty
        )
        remaining = target - have
        if remaining <= 0:
            print(f"{difficulty}: have {have}/{target}, skipping")
            continue

        print(f"{difficulty}: generating {remaining} case(s)")
        while remaining > 0:
            n = min(args.batch, remaining)
            for case in generate(difficulty, n, existing):
                case_id = case.get("id") or f"{difficulty}-{len(existing) + 1}"
                case["id"] = case_id
                case.setdefault("difficulty", difficulty)

                problems = _validate(case, case_id)
                all_problems.extend(problems)

                path = DATASET_DIR / f"{case_id}.json"
                path.write_text(
                    json.dumps(case, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                existing.append(case_id)
                flag = f"  [{len(problems)} problem(s)]" if problems else ""
                print(f"  wrote {path.name}{flag}")
                remaining -= 1
                if remaining <= 0:
                    break

    if all_problems:
        print("\nValidation problems -- fix these before running the eval:")
        for p in all_problems:
            print(f"  - {p}")
    print(
        f"\n{len(list(DATASET_DIR.glob('*.json')))} case(s) in {DATASET_DIR}\n"
        "Read each transcript and confirm its required_tasks are right. "
        "A mislabelled case silently scores a correct system wrong."
    )


if __name__ == "__main__":
    main()
