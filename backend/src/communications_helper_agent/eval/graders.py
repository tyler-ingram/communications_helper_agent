"""Deterministic checks on the pipeline's JSON output.

These run in plain code -- free, instant, and not subject to judge noise.
Anything checkable without judgment belongs here rather than in judge.md;
the judge is reserved for fuzzy matching that genuinely needs a model.

`excerpt_grounded` is the valuable one: the prompt requires every issue to
carry a `source_excerpt` quoted from the transcript, so we can verify that
quote really appears. A model that invents an issue usually has to invent its
justification too, which makes fabrication catchable by string search.
"""

from __future__ import annotations

import json
import re
import unicodedata

VALID_TYPES = {"bug", "feature", "task", "question"}
VALID_CONFIDENCE = {"high", "low", None}

REQUIRED_FIELDS = {
    "title",
    "description",
    "type",
    "tags",
    "priority",
    "assignee",
    "assignee_confidence",
    "suggested_repo",
    "source_excerpt",
    "status",
}


def extract_issues(raw: str) -> tuple[list[dict] | None, str | None]:
    """Pull the JSON array out of a model response.

    The prompt asks the model to think before emitting JSON, so the array is
    usually preceded by prose and often fenced. Returns (issues, error).
    """
    if not raw or not raw.strip():
        return None, "empty response"

    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.S)
    candidate = fenced.group(1) if fenced else None

    if candidate is None:
        start, end = raw.find("["), raw.rfind("]")
        if start == -1 or end == -1 or end < start:
            return None, "no JSON array found in response"
        candidate = raw[start : end + 1]

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        return None, f"malformed JSON: {exc}"

    if not isinstance(parsed, list):
        return None, f"expected a JSON array, got {type(parsed).__name__}"
    if not all(isinstance(i, dict) for i in parsed):
        return None, "array contains non-object entries"
    return parsed, None


def _normalize(text: str) -> str:
    """Collapse whitespace and smart quotes for excerpt matching.

    Models routinely re-type a quote with a curly apostrophe or different line
    wrapping. That is not fabrication, so it shouldn't be scored as such.
    """
    text = unicodedata.normalize("NFKC", text)
    for smart, plain in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"')):
        text = text.replace(smart, plain)
    return re.sub(r"\s+", " ", text).strip().lower()


def check_schema(issues: list[dict]) -> tuple[float, list[str]]:
    """Every issue carries exactly the required fields."""
    problems = []
    for i, issue in enumerate(issues):
        missing = REQUIRED_FIELDS - set(issue)
        extra = set(issue) - REQUIRED_FIELDS
        if missing:
            problems.append(f"issue[{i}] missing {sorted(missing)}")
        if extra:
            problems.append(f"issue[{i}] unexpected {sorted(extra)}")
    return (1.0 if not problems else 0.0), problems


def check_fields(issues: list[dict]) -> tuple[float, list[str]]:
    """Field values are in range and of the right type.

    Scored as a fraction rather than all-or-nothing: one bad priority out of
    six issues shouldn't read the same as every field being wrong.
    """
    problems: list[str] = []
    checks = 0
    failures = 0

    for i, issue in enumerate(issues):
        checks += 4

        if issue.get("type") not in VALID_TYPES:
            failures += 1
            problems.append(f"issue[{i}] type={issue.get('type')!r} not in {VALID_TYPES}")

        prio = issue.get("priority")
        if not isinstance(prio, int) or isinstance(prio, bool) or not 1 <= prio <= 5:
            failures += 1
            problems.append(f"issue[{i}] priority={prio!r} not an int in 1..5")

        # The prompt is explicit: newly proposed issues are always "proposed".
        # "open"/"closed" only exist after a human files the real issue.
        if issue.get("status") != "proposed":
            failures += 1
            problems.append(f"issue[{i}] status={issue.get('status')!r} != 'proposed'")

        tags = issue.get("tags")
        if not isinstance(tags, list) or len(tags) > 4:
            failures += 1
            problems.append(f"issue[{i}] tags must be a list of 0-4, got {tags!r}")
        elif not all(isinstance(t, str) for t in tags):
            failures += 1
            problems.append(f"issue[{i}] tags contains non-strings")

    if checks == 0:
        return 1.0, []
    return (checks - failures) / checks, problems


def check_excerpts(issues: list[dict], transcript: str) -> tuple[float, list[str]]:
    """Every source_excerpt actually appears in the transcript.

    This is the anti-fabrication check. An invented issue usually needs an
    invented quote to justify it, and an invented quote won't be found here.
    """
    if not issues:
        return 1.0, []

    haystack = _normalize(transcript)
    problems = []
    grounded = 0

    for i, issue in enumerate(issues):
        excerpt = issue.get("source_excerpt")
        if not isinstance(excerpt, str) or not excerpt.strip():
            problems.append(f"issue[{i}] has no source_excerpt")
            continue
        if _normalize(excerpt) in haystack:
            grounded += 1
        else:
            problems.append(
                f"issue[{i}] source_excerpt not found in transcript: "
                f"{excerpt[:70]!r}"
            )

    return grounded / len(issues), problems


def check_assignee_safety(
    issues: list[dict], transcript: str
) -> tuple[float, list[str]]:
    """Assignees are real speakers, and confidence is consistent.

    The prompt says to leave assignee null rather than guess, because a wrong
    name is worse than a blank field downstream. Two ways to fail: naming
    somebody who never spoke, or claiming "high" confidence on a null.
    """
    if not issues:
        return 1.0, []

    speakers = {
        _normalize(m.group(1))
        for m in re.finditer(r"^\s*([A-Z][\w'-]*)\s*:", transcript, re.M)
    }
    problems = []
    safe = 0

    for i, issue in enumerate(issues):
        assignee = issue.get("assignee")
        confidence = issue.get("assignee_confidence")
        ok = True

        if confidence not in VALID_CONFIDENCE:
            ok = False
            problems.append(
                f"issue[{i}] assignee_confidence={confidence!r} not in "
                f"{{'high', 'low', None}}"
            )

        if assignee is None:
            # Null assignee must not claim high confidence.
            if confidence == "high":
                ok = False
                problems.append(f"issue[{i}] assignee is null but confidence is 'high'")
        else:
            if not isinstance(assignee, str) or not assignee.strip():
                ok = False
                problems.append(f"issue[{i}] assignee={assignee!r} is not a name")
            elif speakers and _normalize(assignee) not in speakers:
                # Named somebody who never spoke -- the exact failure the
                # prompt's "never guess a name" rule exists to prevent.
                ok = False
                problems.append(
                    f"issue[{i}] assignee={assignee!r} is not a speaker in the "
                    "transcript"
                )

        safe += ok

    return safe / len(issues), problems


def grade_deterministic(raw: str, transcript: str) -> dict:
    """Run every code-checkable grader. Returns scores plus problem detail."""
    issues, parse_error = extract_issues(raw)

    if issues is None:
        # Unparseable output fails every structural check, but the judge still
        # sees the raw text -- a correct answer in the wrong format should lose
        # schema points, not be silently treated as empty.
        return {
            "issues": None,
            "parse_error": parse_error,
            "scores": {
                "schema_valid": 0.0,
                "fields_valid": 0.0,
                "excerpt_grounded": 0.0,
                "assignee_safe": 0.0,
            },
            "problems": [f"parse: {parse_error}"],
        }

    schema, p1 = check_schema(issues)
    fields, p2 = check_fields(issues)
    excerpts, p3 = check_excerpts(issues, transcript)
    assignees, p4 = check_assignee_safety(issues, transcript)

    return {
        "issues": issues,
        "parse_error": None,
        "scores": {
            "schema_valid": schema,
            "fields_valid": fields,
            "excerpt_grounded": excerpts,
            "assignee_safe": assignees,
        },
        "problems": p1 + p2 + p3 + p4,
    }
