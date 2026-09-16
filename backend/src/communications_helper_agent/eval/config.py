"""Shared paths, models, and prompt loading for the eval harness."""

from __future__ import annotations

from pathlib import Path

# backend/src/communications_helper_agent/eval/
EVAL_DIR = Path(__file__).parent
PROMPTS_DIR = EVAL_DIR / "prompts"
DATASET_DIR = EVAL_DIR / "dataset"

# backend/ -- results live outside src/ so generated output isn't packaged.
BACKEND_ROOT = EVAL_DIR.parents[2]
RESULTS_ROOT = BACKEND_ROOT / ".claude" / "hillclimb" / "summarize"

# Writes the dataset. Strong model: transcript quality is the ceiling on the
# eval's usefulness.
GENERATOR_MODEL = "claude-opus-5"

# Under test. Override with --model.
SUMMARIZER_MODEL = "claude-opus-5"

# Grades. Deliberately a different tier from the summarizer: a judge from the
# same model as the system under test tends to prefer outputs resembling its own.
JUDGE_MODEL = "claude-sonnet-5"

DIFFICULTY_MIX = {"clean": 3, "messy": 4, "hard": 2, "edge": 1}

# Ordered: the first entry is the headline metric in the report.
METRICS = [
    {"id": "task_recall", "label": "Recall", "kind": "judge", "scale": 1},
    {"id": "task_precision", "label": "Precision", "kind": "judge", "scale": 1},
    {"id": "faithfulness", "label": "Faithful", "kind": "judge", "scale": 1},
    {"id": "coverage", "label": "Coverage", "kind": "judge", "scale": 1},
]


def load_prompt(name: str) -> str:
    """Read a prompt file from prompts/."""
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def load_summarize_prompt() -> str:
    """The production prompt under test.

    Everything below the marker line is the prompt; the header is documentation.
    """
    text = load_prompt("summarize.md")
    marker = "--- SYSTEM PROMPT BELOW THIS LINE ---"
    if marker in text:
        text = text.split(marker, 1)[1]
    return text.strip()
