"""Shared paths, models, metrics, and prompt loading for the eval harness."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# backend/src/communications_helper_agent/eval/
EVAL_DIR = Path(__file__).parent
PROMPTS_DIR = EVAL_DIR / "prompts"
DATASET_DIR = EVAL_DIR / "dataset"

# backend/ -- results live outside src/ so generated output isn't packaged.
BACKEND_ROOT = EVAL_DIR.parents[2]
RESULTS_ROOT = BACKEND_ROOT / ".claude" / "hillclimb" / "meeting_to_issues"

# Everything runs on LM Studio -- no API key, no per-case cost.
#
# None means "whatever llm.client.DEFAULT_MODEL resolves to" ($LM_MODEL, else
# qwen/qwen3-4b-2507). Override the pipeline per run with --model.
PIPELINE_MODEL: str | None = os.getenv("LM_MODEL") or None


# Mirrors llm/client.py's default. Deliberately duplicated rather than
# imported: `from ..llm.client import DEFAULT_MODEL` pulls in llm/__init__,
# which imports service.py, which imports mcp/github.py -- and that module
# raises at import time when GITHUB_PERSONAL_ACCESS_TOKEN is unset. The eval
# never touches GitHub, so it shouldn't need a GitHub token to start.
# Re-point at the import once that module defers its token check.
FALLBACK_MODEL = "qwen/qwen3-4b-2507"


def _default_judge_model() -> str:
    """The judge's model.

    Prefer a model distinct from the pipeline's: a judge grading output from
    its own weights tends to prefer output resembling what it would have
    written. Set $JUDGE_MODEL to a second local model if you have one loaded.
    Falling back to the pipeline model is workable but makes check_judge.py
    load-bearing rather than merely prudent.
    """
    return os.getenv("JUDGE_MODEL") or PIPELINE_MODEL or FALLBACK_MODEL


JUDGE_MODEL = _default_judge_model()

# Writes the dataset. Same local model -- case quality is the ceiling on what
# the eval can tell you, so read what it produces before trusting a score.
GENERATOR_MODEL = os.getenv("GENERATOR_MODEL") or JUDGE_MODEL

# LM Studio context window, matching llm/client.py.
CONTEXT_LENGTH = 128000

DIFFICULTY_MIX = {"clean": 3, "messy": 4, "hard": 2, "edge": 1}

# Ordered: the first entry is the report's headline metric.
#
# The last four are graded by code -- deterministic, free, and not subject to
# judge noise. The first three need fuzzy matching ("fix slow search" vs
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

    Loaded straight off disk rather than with a normal import. Importing
    `llm.system_prompts` any other way first executes `llm/__init__`, which
    imports service.py -> mcp/github.py, and that module raises at import time
    when GITHUB_PERSONAL_ACCESS_TOKEN is unset. The eval never touches GitHub,
    so it shouldn't need a GitHub token to read a prompt string.

    Replace this with a plain import once mcp/github.py defers its token check.
    """
    import importlib.util

    path = EVAL_DIR.parent / "llm" / "system_prompts.py"
    spec = importlib.util.spec_from_file_location("_system_prompts", path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MEETING_TO_ISSUES_PROMPT
