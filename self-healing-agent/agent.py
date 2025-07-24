from google.adk.agents import Agent

from .prompt import agent_instruction
from .tools.tools import get_current_date, analysis_agent_tool , jira_agent_tool, code_fixer_agent_tool 


root_agent = Agent(
    model="gemini-2.5-flash",
    name="self_healing_agent",
    instruction=agent_instruction,
    tools=[
        analysis_agent_tool,
        jira_agent_tool, 
        code_fixer_agent_tool,
        get_current_date
    ],
)