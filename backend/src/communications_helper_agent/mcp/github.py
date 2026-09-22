from dotenv import load_dotenv
import os
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
import asyncio
import httpx2
from contextlib import asynccontextmanager
import lmstudio as lms
import json
load_dotenv()

github_token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
if not github_token:
    raise ValueError("GITHUB_PERSONAL_ACCESS_TOKEN is not set")

@asynccontextmanager
async def connect_to_github_mcp():
    url = "https://api.githubcopilot.com/mcp/"
    headers = {"Authorization": f"Bearer {github_token}"}
    async with httpx2.AsyncClient(headers=headers) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

def extract_json(result):
    for item in result.content:
        if hasattr(item, "text"):
            return json.loads(item.text)

    return {"error": "No text content returned"}

def extract_text(result):
    return "\n".join(
        item.text
        for item in result.content
        if hasattr(item, "text")
    )

def get_me_tool(session):
    async def get_me():
        result = await session.call_tool(
            "get_me",
            {}
        )
        print(result)
        print(result.content)
        return extract_json(result)
    get_me.__name__ = "get_me"
    get_me.__doc__ = """
    Get the authenticated user's GitHub username.
    """
    return get_me
def search_repositories_tool(session):
    async def search_repositories(
        query: str,
    ):
        result = await session.call_tool(
            "search_repositories",
            {
                "query": query,
            }
        )
        return extract_json(result)
    search_repositories.__name__ = "search_repositories"
    search_repositories.__doc__ = """
    Return a list of repositories matching the given query.
    """
    return search_repositories
def search_issues_tool(session):
    async def search_issues(
        owner: str,
        repo: str,
        query: str,
    ):
        result = await session.call_tool(
            "search_issues",
            {
                "owner": owner,
                "repo": repo,
                "query": query,
            }
        )

        return extract_json(result)
    search_issues.__name__ = "search_issues"
    search_issues.__doc__ = """
    Return a list of issues in a repository matching the given query.
    """
    return search_issues
def create_github_issue_tool(session):

    async def create_github_issue(
        owner: str,
        repo: str,
        title: str,
        body: str,
        tags: list[str] | None = None,
    ):
        try:
            result = await session.call_tool(
                "issue_write",
                {
                    "method": "create",
                    "tags": tags,
                    "owner": owner,
                    "repo": repo,
                    "title": title,
                    "body": body,
                },
            )
            return extract_text(result)
        except Exception as e:
            print(type(e).__name__)
            print(str(e))
            raise
    create_github_issue.__name__ = "create_github_issue"
    create_github_issue.__doc__ = """
    Create a GitHub issue in a repository.

    Use this when a meeting action item should become a new GitHub issue.
    """
    return create_github_issue

def mcp_type_to_python(schema: dict):
    """Convert an MCP JSON-schema type to a Python type."""
    type_map = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }
    return type_map.get(schema.get("type"), str)
