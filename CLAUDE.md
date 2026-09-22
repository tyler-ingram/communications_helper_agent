# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Desktop app that turns unstructured meeting transcripts into GitHub issues. An Electron frontend talks to a local FastAPI backend, which drives a local LLM (LM Studio) that calls GitHub's hosted MCP server as tools. There is no test suite or linter configured.

## Commands

Run from `frontend/` (the npm scripts delegate to `frontend/scripts/monorepo-scripts.py`, which orchestrates both workspaces):

- `npm run setup`: `uv sync` in `backend/`, `lms get qwen/qwen3-4b-2507`, and `npm install` in `frontend/`.
- `npm run start`: brings up the LM Studio daemon and server (`lms daemon up`, `lms server start`), starts uvicorn in the background (`communications_helper_agent.api.server:app` on `127.0.0.1:8743`), then runs Electron in the foreground. Uvicorn is terminated when Electron exits.

Backend only (from `backend/`): `uv run uvicorn communications_helper_agent.api.server:app --host 127.0.0.1 --port 8743`. `src/communications_helper_agent/example_mcp.py` is a standalone script for testing the MCP connection using `GITHUB_PERSONAL_ACCESS_TOKEN`.

Requires Python 3.13+, `uv`, Node, and LM Studio (`lms` CLI). Copy `backend/.env.example` to `backend/.env`; `LM_MODEL` selects the model and `GITHUB_OAUTH_CLIENT_ID`/`GITHUB_OAUTH_CLIENT_SECRET` come from each developer's own GitHub OAuth App (callback URL `commshelper://oauth/callback`, see README).

## Architecture

**Request flow:** renderer (`frontend/renderer.js`) → `window.api` (contextBridge in `preload.js`) → IPC handlers in `frontend/main.js` → HTTP to `http://127.0.0.1:8743` → `backend/.../api/server.py` → `llm/service.py:ask_with_tools` → LM Studio model with GitHub MCP tools.

**GitHub OAuth (split across both halves):**
- `main.js` registers the `commshelper://` custom protocol, opens the GitHub authorize URL in the system browser, and receives the callback via `open-url` / `second-instance` argv (the app holds a single-instance lock for this).
- The backend owns the client secret: `/auth/state` issues a CSRF state (in-memory, 10 min TTL), `/auth/client-id` exposes the ID, and `/auth/exchange` swaps code + state for a token. The secret must never reach the Electron/renderer code.
- The token lives only in the main process, persisted encrypted via `safeStorage` in `userData/github-token.enc`, and is never sent to the renderer. Main attaches it to backend calls as a `Authorization: Bearer` header; backend endpoints (`_get_bearer_token`) are stateless and pass it through to the MCP connection.

**LLM + tools:** `llm/client.py:get_model` opens an async LM Studio client (128k context). `ask_with_tools` opens a per-request MCP session (`mcp/github.py:connect_to_github_mcp`, streamable HTTP to `api.githubcopilot.com/mcp/`) and passes wrapper functions (`get_me`, `search_repositories`, `search_issues`, `create_github_issue`) to `model.act`. LM Studio derives each tool's schema from the wrapper's signature, `__name__`, and `__doc__`, so those matter. To add a tool, write a wrapper in `mcp/github.py` following the existing pattern and register it in the `tools` list in `service.py`.

**Prompts:** all system prompts live in `llm/system_prompts.py`; `MEETING_TO_ISSUES_PROMPT` is used by both `/transcript/text` and `/transcript/file`.
