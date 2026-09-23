import os
import secrets
import time
import asyncio
import base64
import io
import traceback

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

from communications_helper_agent.llm.service import ask_with_tools
from communications_helper_agent.llm.system_prompts import (
    MEETING_TO_ISSUES_PROMPT, 
    CREATE_ISSUES_PROMPT, 
    MEETING_SUMMARY_PROMPT
)
from communications_helper_agent.mcp.github import connect_to_github_mcp, get_me_tool

load_dotenv()

GITHUB_OAUTH_CLIENT_ID = os.getenv("GITHUB_OAUTH_CLIENT_ID")
GITHUB_OAUTH_CLIENT_SECRET = os.getenv("GITHUB_OAUTH_CLIENT_SECRET")

STATE_TTL_SECONDS = 600

app = FastAPI()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()  # still prints for whoever has terminal access
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )


# In-memory CSRF state store: state -> expiry timestamp. Fine for a single-user
# local desktop app talking to a loopback-only server.
_pending_states: dict[str, float] = {}


def _prune_expired_states() -> None:
    now = time.time()
    expired = [state for state, expiry in _pending_states.items() if expiry < now]
    for state in expired:
        _pending_states.pop(state, None)


def _get_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    return auth_header[len("bearer "):].strip()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/auth/client-id")
async def auth_client_id():
    if not GITHUB_OAUTH_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GITHUB_OAUTH_CLIENT_ID is not configured")
    return {"client_id": GITHUB_OAUTH_CLIENT_ID}


@app.get("/auth/state")
async def auth_state():
    _prune_expired_states()
    state = secrets.token_urlsafe(32)
    _pending_states[state] = time.time() + STATE_TTL_SECONDS
    return {"state": state}


class AuthExchangeRequest(BaseModel):
    code: str
    state: str


@app.post("/auth/exchange")
async def auth_exchange(body: AuthExchangeRequest):
    _prune_expired_states()
    if body.state not in _pending_states:
        raise HTTPException(status_code=400, detail="Unknown or expired state parameter")
    _pending_states.pop(body.state, None)

    if not GITHUB_OAUTH_CLIENT_ID or not GITHUB_OAUTH_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="GitHub OAuth app is not configured on the server")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_OAUTH_CLIENT_ID,
                "client_secret": GITHUB_OAUTH_CLIENT_SECRET,
                "code": body.code,
                "redirect_uri": "commshelper://oauth/callback",
            },
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="GitHub token exchange failed")

    payload = response.json()
    if "error" in payload:
        raise HTTPException(status_code=400, detail=payload.get("error_description", payload["error"]))
    if "access_token" not in payload:
        raise HTTPException(status_code=502, detail="GitHub token exchange did not return an access token")

    return payload


@app.get("/auth/me")
async def auth_me(request: Request):
    token = _get_bearer_token(request)
    async with connect_to_github_mcp(token) as session:
        me = await get_me_tool(session)()
    return me


@app.post("/transcript/text")
async def transcript_text(request: Request):
    token = _get_bearer_token(request)
    body = await request.json()
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="Missing transcript text")

    # Run one after the other so LM Studio doesn't crash from concurrent requests
    issues_result = await ask_with_tools(prompt=text, system=MEETING_TO_ISSUES_PROMPT, github_token=token)
    summary_result = await ask_with_tools(prompt=text, system=MEETING_SUMMARY_PROMPT, github_token=token)
    
    return {
        "result": _extract_text(issues_result), 
        "summary": _extract_text(summary_result)
    }


@app.post("/transcript/file")
async def transcript_file(request: Request):
    token = _get_bearer_token(request)
    body = await request.json()
    filename = body.get("filename", "")
    b64content = body.get("content", "")
    
    if not b64content:
        raise HTTPException(status_code=400, detail="Missing file content")

    try:
        file_bytes = base64.b64decode(b64content)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 content")

    text = ""
    if filename.lower().endswith(".pdf"):
        if not PdfReader:
            raise HTTPException(status_code=500, detail="pypdf is not installed")
        try:
            pdf = PdfReader(io.BytesIO(file_bytes))
            text = "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {str(e)}")
    else:
        text = file_bytes.decode("utf-8", errors="replace")

    if not text.strip():
        raise HTTPException(status_code=400, detail="No readable text found in file")

    # Run one after the other so LM Studio doesn't crash from concurrent requests
    issues_result = await ask_with_tools(prompt=text, system=MEETING_TO_ISSUES_PROMPT, github_token=token)
    summary_result = await ask_with_tools(prompt=text, system=MEETING_SUMMARY_PROMPT, github_token=token)
    
    return {
        "result": _extract_text(issues_result), 
        "summary": _extract_text(summary_result)
    }


def _extract_text(result) -> str:
    if isinstance(result, list):
        return "\n".join(getattr(item, "text", "") for item in result)
    return str(result)

@app.post("/issues/accepted")
async def issues_accepted(request: Request):
    token = _get_bearer_token(request)
    body = await request.json()
    issues = body.get("issues", [])
    if not issues:
        raise HTTPException(status_code=400, detail="Missing accepted issues")

    return {"status": "success", "accepted_issues": issues}