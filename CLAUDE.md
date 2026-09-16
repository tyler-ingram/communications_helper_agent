# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Takes a meeting transcript (Zoom, Meet, etc.) and turns it into structured, actionable work:

1. **Extract** — `MEETING_TO_ISSUES_PROMPT` in `llm/system_prompts.py` takes a transcript and emits a JSON array of proposed GitHub issues (title, description, type, tags, priority, assignee, `source_excerpt`, status). One model call; there is no separate summarization step.
2. **File issues** — a human reviews each proposal, then it becomes a real GitHub issue.

Step 2 is deliberately **not** an LLM call and **not** MCP: step 1 already emits structured issues, so filing them is a deterministic loop over the GitHub REST API (PyGithub or `httpx`). Routing it through a model adds latency, cost, and a chance of inventing work. MCP solves tool *discovery* for interactive agents; this pipeline knows its one operation at build time. (MCP would earn its place only if Claude Code itself were to manage the repo interactively — a separate feature.)

**Models run locally through LM Studio**, not the Claude API — `llm/client.py`, `$LM_MODEL`, default `qwen/qwen3-4b-2507`. The only Claude API calls in the repo are in the eval harness (dataset generation and the judge). Don't add `anthropic` calls to the pipeline.

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

- **The eval runs the real pipeline.** `run_pipeline()` calls `llm.service.ask()` with the prompt imported live from `llm/system_prompts.py`. Never copy the prompt into the eval — importing it is what stops the eval measuring a stale version.
- **Grading is split.** `graders.py` handles everything checkable in code (schema, field ranges, `source_excerpt` grounding, assignee safety); `judge.md` handles only fuzzy matching (recall, precision, faithfulness). Don't move a deterministic check into the judge — it costs money and adds noise to an exact answer.
- **`excerpt_grounded` is the anti-fabrication check.** The prompt requires every issue to quote the transcript, so an invented issue usually carries an invented quote, which fails a string search. Free hallucination detection.
- **Cases are `{data, solution_criteria}`.** `solution_criteria` holds checkable claims (`required_tasks` with verbatim `evidence` quotes, `must_mention`, `must_not_contain`), not one golden output — two correct issue lists can be worded completely differently.
- **Seven independent metrics**, not one blended score. Recall and precision regressions have different fixes, so a single number would hide which one moved.
- **The judge is `claude-sonnet-5`**, a different family from the local pipeline model — a judge sharing a model with the system under test prefers outputs resembling its own.
- **`check_judge.py` must pass before any full run.** It builds issue lists whose correct score is known by construction (an oracle assembled from the answer key, an empty array, a wrong-meeting list, a rejected proposal, a prompt injection) and checks the judge agrees. Scores from an unverified judge measure the judge's blind spots.
- **Generated cases are not ground truth.** The generator writes both transcript and labels; `_validate` checks structure only. Read the cases.
- Failed attempts go to `errors.jsonl` with a failure class, never `results.jsonl` — a plumbing error scored as 0 is indistinguishable from a genuine model failure and would block resume. If LM Studio is down, every case lands there.

## Environment

`backend/.env` (gitignored, copied from `.env.example`) holds `LM_MODEL` for the pipeline. `llm/client.py` calls `load_dotenv()`, so that one is picked up automatically.

The eval harness also needs `ANTHROPIC_API_KEY` for the generator and judge. Nothing loads it for them yet — export it, or add a `load_dotenv()` call in the eval entry points.

## Claude API usage

This project calls the Claude API, so load the `claude-api` skill before writing or reviewing any code that touches models, the `anthropic` SDK, pricing, or token limits — do not answer those from memory.
