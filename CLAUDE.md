# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Takes a meeting transcript (Zoom, Meet, etc.) and turns it into structured, actionable work:

1. **Extract** — `MEETING_TO_ISSUES_PROMPT` in `llm/system_prompts.py` takes a transcript and emits a JSON array of proposed GitHub issues (title, description, type, tags, priority, assignee, `source_excerpt`, status). One model call; there is no separate summarization step.
2. **File issues** — `CREATE_ISSUES_PROMPT` + `llm.service.ask_with_tools()` drive a tool-calling loop against GitHub's hosted MCP server (`mcp/github.py`, `api.githubcopilot.com/mcp/`), with `get_me` / `search_repositories` / `search_issues` / `create_github_issue`. Only issues marked approved get filed.

**Everything runs locally through LM Studio** — `llm/client.py`, `$LM_MODEL`, default `qwen/qwen3-4b-2507`. There are no Claude API calls anywhere in the repo, including the eval harness, and no `anthropic` dependency. Don't reintroduce one without asking.

There is also an Electron frontend in `frontend/` (a form that submits a text block or file). No test runner or linter yet — those choices are open, so surface them rather than silently picking one.

## Layout

The Python project root is `backend/`, **not** the repo root — `pyproject.toml`, `.python-version`, and `.env` all live there. Run every `uv` command from `backend/`. The Electron app is its own sibling tree in `frontend/`, so keep backend concerns inside `backend/`.

The build backend is `uv_build` with the default src layout: importable package code goes under `backend/src/communications_helper_agent/`.

## Commands

All from `backend/`:

```bash
uv sync                                   # install/lock dependencies
uv run communications-helper-agent        # run the console entry point (-> __init__:main)
uv add <pkg>                              # add a dependency (edits pyproject.toml + uv.lock)
uv add --dev <pkg>                        # add a dev-only dependency
```

Python is pinned to 3.13 (`requires-python = ">=3.13"`).

Eval harness (see `src/communications_helper_agent/eval/README.md`):

```bash
uv run python -m communications_helper_agent.eval.generate_dataset   # write cases (costs money)
uv run python -m communications_helper_agent.eval.check_judge        # verify judge before paying
uv run python -m communications_helper_agent.eval.run_eval --reps 2  # run + grade (needs LM Studio up)
```

No test or lint commands exist yet. When adding them, prefer `uv add --dev pytest` and `uv run pytest` (single test: `uv run pytest tests/test_x.py::test_name`) so tooling stays inside the uv-managed environment.

## Eval harness

`src/communications_helper_agent/eval/` measures the extraction prompt. Its README is the reference; the load-bearing decisions:

- **The eval runs the real prompt.** `load_pipeline_prompt()` reads `MEETING_TO_ISSUES_PROMPT` off disk, so the eval can never measure a stale copy. It loads by file path rather than importing, because importing anything under `llm/` executes `llm/__init__` → `service.py` → `mcp/github.py`, which raises at import time unless `GITHUB_PERSONAL_ACCESS_TOKEN` is set — and the eval never touches GitHub. Two follow-ups worth doing in the app: defer that token check, and fix `llm.service.ask()`, which is broken since `get_model()` became an async context manager. Once `ask()` works, `run_pipeline()` should call it instead of duplicating its body.
- **Grading is split.** `graders.py` handles everything checkable in code (schema, field ranges, `source_excerpt` grounding, assignee safety); `judge.md` handles only fuzzy matching (recall, precision, faithfulness). Don't move a deterministic check into the judge — it adds latency and noise to an exact answer.
- **`excerpt_grounded` is the anti-fabrication check.** The prompt requires every issue to quote the transcript, so an invented issue usually carries an invented quote, which fails a string search. Free hallucination detection.
- **Cases are `{data, solution_criteria}`.** `solution_criteria` holds checkable claims (`required_tasks` with verbatim `evidence` quotes, `must_mention`, `must_not_contain`), not one golden output — two correct issue lists can be worded completely differently.
- **Seven independent metrics**, not one blended score. Recall and precision regressions have different fixes, so a single number would hide which one moved.
- **The judge runs on LM Studio too** (`$JUDGE_MODEL`, falling back to `$LM_MODEL`). When it shares a model with the pipeline it prefers output resembling its own, inflating scores; `run_eval` warns and records `meta.judge_is_pipeline_model`. Point `$JUDGE_MODEL` at a second local model when one is available.
- **`check_judge.py` must pass before any full run.** It builds issue lists whose correct score is known by construction (an oracle assembled from the answer key, an empty array, a wrong-meeting list, a rejected proposal, a prompt injection) and checks the judge agrees. This matters more with a small local judge that may simply be too weak to grade: if the oracle scores below 1.0, raise `$JUDGE_MODEL` rather than touching the prompt.
- **Generated cases are not ground truth.** The generator writes both transcript and labels; `_validate` checks structure only. Read the cases.
- Failed attempts go to `errors.jsonl` with a failure class, never `results.jsonl` — a plumbing error scored as 0 is indistinguishable from a genuine model failure and would block resume. If LM Studio is down, every case lands there.

## Environment

`backend/.env` (gitignored, copied from `.env.example`) holds `LM_MODEL` and `GITHUB_PERSONAL_ACCESS_TOKEN`. Both `llm/client.py` and `eval/config.py` call `load_dotenv()`.

Optional eval overrides: `$JUDGE_MODEL` and `$GENERATOR_MODEL`. No API keys are needed — everything is local.

## LLM usage

All model calls go through LM Studio (`lmstudio` SDK), not the Claude API. Structured output uses `response_format={"type": "json", "json_schema": ...}` on `AsyncLLM.respond()`; there is no `output_config`/`max_tokens`/`thinking` here — those are Anthropic-only parameters.

`mcp/github.py` talks to GitHub's hosted MCP server via `streamable_http_client`, driven by LM Studio's `model.act()` tool loop.
