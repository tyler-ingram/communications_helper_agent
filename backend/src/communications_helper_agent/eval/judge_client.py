"""The judge's model call, against LM Studio.

The judge runs on a local model, so the eval needs no API key and costs
nothing per case.

Two consequences worth knowing:

**The judge and the system under test may be the same model.** A judge grading
output from its own weights prefers output resembling what it would have
written. `check_judge.py` is the mitigation -- it holds the input at a known
quality and verifies the judge reports that quality correctly. Run it after any
judge change. Point $JUDGE_MODEL at a different local model when one is
available.

**Structured output is best-effort, not guaranteed.** The schema is passed to
LM Studio, but a reasoning model (qwen3-*-thinking) emits a `<think>` block
that cannot be schema-constrained, so the server silently disables enforcement
and returns prose with JSON somewhere inside. `_extract_json` handles that. On
a non-reasoning model the schema is enforced and the extraction is a no-op.
"""

from __future__ import annotations

import json
import re
from typing import Any

import lmstudio as lms

# A reasoning model wraps its scratchpad in these before the real answer.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S | re.I)
_UNCLOSED_THINK = re.compile(r"^.*?</think>", re.S | re.I)
_FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def _extract_json(text: str) -> dict:
    """Pull the grade object out of a response.

    On a schema-enforced model the whole response is the object and the first
    `json.loads` succeeds. On a reasoning model it arrives after a `<think>`
    block, sometimes fenced, sometimes with commentary around it.

    Raises ValueError when no JSON object can be found -- never returns a
    default, since a silent default would score the case as though the judge
    had answered.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("judge returned an empty response")

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    stripped = _THINK_BLOCK.sub("", text).strip()
    if "</think>" in stripped.lower():
        # An unclosed or nested block: drop everything up to the last close tag.
        stripped = _UNCLOSED_THINK.sub("", stripped).strip()

    for candidate in _candidates(stripped):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise ValueError(f"no JSON object found in judge response: {text[:300]!r}")


def _candidates(text: str):
    """JSON-object candidates, most likely first."""
    yield text

    fenced = _FENCED.search(text)
    if fenced:
        yield fenced.group(1)

    # The last balanced {...} in the text -- a reasoning model often restates
    # its answer at the end, and the final copy is the one it committed to.
    depth = 0
    end = -1
    for i in range(len(text) - 1, -1, -1):
        ch = text[i]
        if ch == "}":
            if depth == 0:
                end = i
            depth += 1
        elif ch == "{":
            depth -= 1
            if depth == 0 and end != -1:
                yield text[i : end + 1]
                end = -1


def _coerce(grade: dict, schema: dict[str, Any]) -> dict:
    """Coerce numeric fields that came back as strings.

    Only runs when the schema was not enforced. A model writing `"0.5"` instead
    of `0.5` is answering correctly in the wrong type; failing the case over
    that would measure formatting, not grading.
    """
    props = schema.get("properties", {})
    for key, spec in props.items():
        if key not in grade or spec.get("type") != "number":
            continue
        value = grade[key]
        if isinstance(value, bool) or isinstance(value, (int, float)):
            continue
        try:
            grade[key] = float(str(value).strip())
        except (TypeError, ValueError):
            pass  # left as-is; the required-field check below reports it
    return grade


async def judge_call(
    model_key: str,
    system: str,
    user: str,
    schema: dict[str, Any],
    context_length: int = 32768,
) -> tuple[dict, str]:
    """Run one grading call. Returns (parsed_grade, model_key_used)."""
    async with lms.AsyncClient() as client:
        model = await client.llm.model(
            model_key, config={"contextLength": context_length}
        )

        chat = lms.Chat(system)
        chat.add_user_message(user)

        result = await model.respond(chat, response_format=schema)

    try:
        grade = _extract_json(result.content)
    except ValueError as exc:
        raise RuntimeError(f"judge output unusable: {exc}") from exc

    if not getattr(result, "structured", False):
        grade = _coerce(grade, schema)

    missing = [k for k in schema.get("required", []) if k not in grade]
    if missing:
        raise RuntimeError(f"judge omitted required field(s) {missing}: {grade}")

    return grade, model_key
