"""The judge's model call, against LM Studio.

The judge used to run on the Anthropic API. It now runs on a local model, so
the eval needs no API key and costs nothing per case.

One consequence worth knowing: the judge and the system under test are now the
same family of model, and often literally the same weights. A judge grading
output from its own model tends to prefer output that resembles what it would
have written. That is a real bias, and the mitigation is `check_judge.py` --
it holds the input at a known quality and verifies the judge reports that
quality correctly. Run it after any judge change.

If a second model is available locally, prefer pointing $JUDGE_MODEL at a
different one from $LM_MODEL. Any separation helps.
"""

from __future__ import annotations

import json
from typing import Any

import lmstudio as lms

# Ask for JSON directly rather than parsing it out of prose. LM Studio
# constrains generation to the schema, so the parse is deterministic instead of
# depending on the model remembering to emit clean JSON.
RESPONSE_FORMAT_TYPE = "json"


async def judge_call(
    model_key: str,
    system: str,
    user: str,
    schema: dict[str, Any],
    context_length: int = 128000,
) -> tuple[dict, str]:
    """Run one grading call. Returns (parsed_grade, model_key_used).

    Transcripts plus criteria plus an issue list run long, hence the explicit
    context length -- the same one llm/client.py uses.
    """
    async with lms.AsyncClient() as client:
        model = await client.llm.model(
            model_key, config={"contextLength": context_length}
        )

        chat = lms.Chat(system)
        chat.add_user_message(user)

        result = await model.respond(
            chat,
            response_format={"type": RESPONSE_FORMAT_TYPE, "json_schema": schema},
        )

    text = result.content
    try:
        grade = json.loads(text)
    except json.JSONDecodeError as exc:
        # Schema-constrained generation should make this impossible, but a
        # small model under a long prompt can still truncate. Surfacing the
        # raw text matters -- a silent default would score the case as if the
        # judge had answered.
        raise RuntimeError(
            f"judge returned unparseable JSON ({exc}): {text[:300]!r}"
        ) from exc

    missing = [k for k in schema.get("required", []) if k not in grade]
    if missing:
        raise RuntimeError(f"judge omitted required field(s) {missing}: {grade}")

    return grade, model_key
