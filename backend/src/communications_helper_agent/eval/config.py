"""Shared paths, models, metrics, and prompt loading for the eval harness."""

from __future__ import annotations

import os
from pathlib import Path

# backend/src/communications_helper_agent/eval/
EVAL_DIR = Path(__file__).parent
PROMPTS_DIR = EVAL_DIR / "prompts"
DATASET_DIR = EVAL_DIR / "dataset"

# backend/ -- results live outside src/ so generated output isn't packaged.
BACKEND_ROOT = EVAL_DIR.parents[2]
RESULTS_ROOT = BACKEND_ROOT / ".claude" / "hillclimb" / "meeting_to_issues"

# --- The system under test -------------------------------------------------
# Production runs local models through LM Studio (llm/client.py), so the eval
# does too. Measuring claude-opus-5 here would produce numbers that don't
# transfer to what actually ships.
#
# None means "whatever llm.client.DEFAULT_MODEL resolves to" -- normally
# $LM_MODEL, else qwen/qwen3-4b-2507. Override per run with --model.
PIPELINE_MODEL: str | None = os.getenv("LM_MODEL") or None

# --- Models the harness itself uses ----------------------------------------
# These call the Anthropic API and cost money; the pipeline side is free.

# Writes the dataset. Strong model: case quality is the ceiling on how much
# the eval can tell you.
GENERATOR_MODEL = "claude-opus-5"

# Grades the fuzzy half. A judge from the same model as the system under test
# prefers outputs resembling its own -- not a risk here, since the pipeline is
# a local qwen, but keeping them distinct keeps that true if the pipeline
# later moves to the Claude API.
JUDGE_MODEL = "claude-sonnet-5"

DIFFICULTY_MIX = {"clean": 3, "messy": 4, "hard": 2, "edge": 1}

# Ordered: the first entry is the report's headline metric.
#
# The first four are graded by code -- deterministic, free, and not subject to
# judge noise. The last three need fuzzy matching ("fix slow search" vs
# "search performance issue" are the same issue), which is what the judge is
# for. Kept as separate metrics rather than one blended score: a recall drop
# (missed issues) and a precision drop (invented issues) have different fixes.
METRICS = [
    {"id": "issue_recall", "label": "Recall", "kind": "judge", "scale": 1},
    {"id": "issue_precision", "label": "Precision", "kind": "judge", "scale": 1},
    {"id": "faithfulness", "label": "Faithful", "kind": "judge", "scale": 1},
    {"id": "schema_valid", "label": "Schema", "kind": "binary", "scale": 1},
    {"id": "excerpt_grounded", "label": "Grounded", "kind": "binary", "scale": 1},
    {"id": "fields_valid", "label": "Fields", "kind": "binary", "scale": 1},
    {"id": "assignee_safe", "label": "Assignee", "kind": "binary", "scale": 1},
]


def load_prompt(name: str) -> str:
    """Read a prompt file from prompts/."""
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def load_pipeline_prompt() -> str:
    """The production system prompt under test.

    Read from the app's own module rather than copied here, so the eval can
    never drift from what ships. If the partner edits system_prompts.py, the
    next eval run picks it up automatically.
    """
    from ..llm.system_prompts import MEETING_TO_ISSUES_PROMPT

    return MEETING_TO_ISSUES_PROMPT
