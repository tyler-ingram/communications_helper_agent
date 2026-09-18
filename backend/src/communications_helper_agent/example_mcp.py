from communications_helper_agent.llm.service import ask, ask_with_tools
from communications_helper_agent.llm.system_prompts import MEETING_TO_ISSUES_PROMPT, CREATE_ISSUES_PROMPT
import json
import asyncio

def main():
    with open("./transcripts/Meeting started 2026_09_08 08_58 PDT - Notes by Gemini.txt", "r") as file:
        transcript = file.read()
    response = asyncio.run(ask_with_tools(prompt=transcript, system=MEETING_TO_ISSUES_PROMPT))
    text = response[0].text
    data = json.loads(text)
    data[0]["status"] = "approved"
    data[0]["suggested_repo"] = "communications_helper_agent"
    approved_issues = [issue for issue in data if issue.get("status") == "approved"]
    prompt = f"""
Here is the approved issue data:
<issue>
{approved_issues}
</issue>
Use the GitHub tools according to the instructions.
"""
    tool_response = asyncio.run(ask_with_tools(prompt, system=CREATE_ISSUES_PROMPT))
    print(tool_response)

main()