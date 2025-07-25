
from google.adk.agents import Agent
import json
from typing import Any, Dict

from .prompt import agent_instruction
from .tools.tools import get_current_date, analysis_agent_tool , jira_agent_tool, code_fixer_agent_tool 

def safe_json_serialize(obj: Any) -> str:
    """
    Safely serialize objects to JSON string, handling non-serializable objects.
    """
    def default_serializer(o):
        if hasattr(o, '__dict__'):
            return {k: v for k, v in o.__dict__.items() if not k.startswith('_')}
        elif hasattr(o, 'dict'):
            try:
                return o.dict()
            except:
                return str(o)
        else:
            return str(o)
    
    try:
        return json.dumps(obj, default=default_serializer, indent=2)
    except Exception as e:
        return f"Serialization error: {str(e)}"

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