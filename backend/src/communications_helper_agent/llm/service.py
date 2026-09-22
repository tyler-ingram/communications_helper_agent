from lmstudio import Chat
from communications_helper_agent.mcp.github import connect_to_github_mcp, create_github_issue_tool, search_repositories_tool, search_issues_tool, get_me_tool
from .client import get_model



def ask(prompt: str, *, system: str | None = None, model_key: str | None = None) -> str:
    """Send a single prompt to the model and return its text response."""
    model = get_model(model_key)

    if system:
        chat = Chat(system)
        chat.add_user_message(prompt)
        result = model.respond(chat)
    else:
        result = model.respond(prompt)

    return result.content

async def ask_with_tools(prompt: str, *, system: str | None = None, model_key: str | None = None, github_token: str | None = None) -> str:
    """Ask with github mcp tools for getting the user name, searching repos, searching issues and creating issues."""
    async with get_model(model_key) as model:
        async with connect_to_github_mcp(github_token) as session:

            tools = [
                get_me_tool(session),
                search_repositories_tool(session),
                search_issues_tool(session),
                create_github_issue_tool(session)
            ]
            if system:
                chat = Chat(system)
                chat.add_user_message(prompt)
                await model.act(chat, tools=tools, on_message=chat.append)
            else:
                chat = Chat()
                chat.add_user_message(prompt)
                await model.act(chat, tools=tools, on_message=chat.append)
            return chat._get_last_message(role="assistant").content