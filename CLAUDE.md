# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Takes a meeting transcript (Zoom, Meet, etc.) and turns it into structured, actionable work in two LLM stages:

1. **Summarize** — transcript in, summary out, preserving every actionable subtask discussed. This is the stage currently under development.
2. **Create issues** — the extracted subtasks become GitHub issues.

Stage 2 is deliberately **not** an LLM call and **not** MCP: by that point stage 1 has produced structured subtasks, so turning them into issues is a deterministic loop over the GitHub REST API (PyGithub or `httpx`). Routing it through a model adds latency, cost, and a chance of inventing tasks. MCP solves tool *discovery* for interactive agents; this pipeline knows its one operation at build time. (MCP would earn its place only if Claude Code itself were to manage the repo interactively — a separate feature from the pipeline.)

Outside the eval harness the repo is still a scaffold: no web framework, no test runner, no linter. Those choices are open — surface them rather than silently picking one.

## Layout

The Python project root is `backend/`, **not** the repo root — `pyproject.toml`, `.python-version`, and `.env` all live there. Run every `uv` command from `backend/`. The `backend/` nesting implies a future sibling frontend, so keep backend concerns inside it.

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
uv run python -m communications_helper_agent.eval.run_eval --reps 2  # run + grade
```

No test or lint commands exist yet. When adding them, prefer `uv add --dev pytest` and `uv run pytest` (single test: `uv run pytest tests/test_x.py::test_name`) so tooling stays inside the uv-managed environment.

## Eval harness

`src/communications_helper_agent/eval/` measures the stage-1 prompt. Its README is the reference; the load-bearing decisions:

- **`prompts/summarize.md` is a placeholder owned by the partner** — the artifact under test, not part of the harness. Everything below its marker line is the system prompt; the `{transcript}` placeholder must survive, since the runner formats against it.
- **Cases are `{data, solution_criteria}`.** `solution_criteria` holds checkable claims (`required_tasks` with verbatim `evidence` quotes, `must_mention`, `must_not_contain`), not one golden summary — two correct summaries can be worded completely differently.
- **Four independent metrics**, not one blended score: recall (headline), precision, faithfulness, coverage. Recall and precision regressions have different fixes, so a single number would hide which one moved.
- **The judge runs on a different model** (`claude-sonnet-5`) than the summarizer (`claude-opus-5`) — a judge from the same model prefers outputs resembling its own.
- **`check_judge.py` must pass before any full run.** It feeds the judge an oracle, an empty string, a refusal, a confident summary of the wrong meeting, and a prompt injection. Scores from an unverified judge measure the judge's blind spots.
- **Generated cases are not ground truth.** The generator writes both transcript and labels; `_validate` checks structure only. Read the cases.
- Failed attempts go to `errors.jsonl` with a failure class, never `results.jsonl` — a plumbing error scored as 0 is indistinguishable from a genuine model failure and would block resume.

## Environment

`backend/.env` (gitignored, copied from `.env.example`) holds `ANTHROPIC_API_KEY`. The SDK reads it from the environment; nothing loads the file automatically yet, so export it or add a `python-dotenv` call.

## Claude API usage

This project calls the Claude API, so load the `claude-api` skill before writing or reviewing any code that touches models, the `anthropic` SDK, pricing, or token limits — do not answer those from memory.
