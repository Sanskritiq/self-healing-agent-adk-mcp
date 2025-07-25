from datetime import datetime
import os
import json
from typing import Any, Dict

from google.adk.agents import Agent
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.langchain_tool import LangchainTool
from google.adk.tools.mcp_tool import MCPToolset, StreamableHTTPConnectionParams
from langchain_community.tools import StackExchangeTool
from langchain_community.utilities import StackExchangeAPIWrapper
from toolbox_core import ToolboxSyncClient
from pydantic import AnyUrl

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ----- Utility Functions -----
def get_current_date() -> dict:
    """Get the current date in the format YYYY-MM-DD"""
    return {"current_date": datetime.now().strftime("%Y-%m-%d")}

def serialize_tool_response(response: Any) -> Dict[str, Any]:
    """
    Convert tool responses to JSON-serializable format.
    Handles AnyUrl and other non-serializable objects.
    """
    if isinstance(response, dict):
        return {k: serialize_tool_response(v) for k, v in response.items()}
    elif isinstance(response, list):
        return [serialize_tool_response(item) for item in response]
    elif isinstance(response, AnyUrl):
        return str(response)
    elif hasattr(response, '__dict__'):
        # For objects with attributes, convert to dict
        result = {}
        for key, value in response.__dict__.items():
            if not key.startswith('_'):  # Skip private attributes
                result[key] = serialize_tool_response(value)
        return result
    elif hasattr(response, 'dict'):
        # For Pydantic models
        try:
            return serialize_tool_response(response.dict())
        except:
            return str(response)
    else:
        # For primitive types and other serializable objects
        try:
            json.dumps(response)  # Test if it's serializable
            return response
        except (TypeError, ValueError):
            return str(response)

# ----- Wrapper Classes for Tools -----
class SerializableMCPToolset:
    """Wrapper for MCPToolset that ensures JSON serializable responses"""
    
    def __init__(self, mcp_toolset: MCPToolset):
        self.mcp_toolset = mcp_toolset
    
    def __getattr__(self, name):
        """Delegate attribute access to the wrapped toolset"""
        attr = getattr(self.mcp_toolset, name)
        if callable(attr):
            def wrapper(*args, **kwargs):
                result = attr(*args, **kwargs)
                return serialize_tool_response(result)
            return wrapper
        return attr

class SerializableLangchainTool:
    """Wrapper for LangchainTool that ensures JSON serializable responses"""
    
    def __init__(self, langchain_tool: LangchainTool):
        self.langchain_tool = langchain_tool
    
    def __getattr__(self, name):
        """Delegate attribute access to the wrapped tool"""
        attr = getattr(self.langchain_tool, name)
        if callable(attr):
            def wrapper(*args, **kwargs):
                result = attr(*args, **kwargs)
                return serialize_tool_response(result)
            return wrapper
        return attr

# ----- Initialize Base Tools -----

# Search Agent for web searches
search_agent = Agent(
    model="gemini-2.5-flash",
    name="search_agent",
    instruction="""
    You're a specialist in Google Search. Focus on finding relevant technical documentation,
    bug reports, and solutions for programming issues. Provide concise, actionable information.
    Always return results in a JSON-serializable format.
    """,
    tools=[google_search],
)
search_tool = AgentTool(search_agent)

# StackOverflow tool for technical Q&A
try:
    stack_exchange_tool = StackExchangeTool(api_wrapper=StackExchangeAPIWrapper())
    stackoverflow_tool = SerializableLangchainTool(LangchainTool(stack_exchange_tool))
except Exception as e:
    print(f"Warning: Could not initialize StackOverflow tool: {e}")
    stackoverflow_tool = None

# Toolbox for JIRA operations
TOOLBOX_URL = os.getenv("MCP_TOOLBOX_URL", "http://127.0.0.1:5000")
try:
    toolbox = ToolboxSyncClient(TOOLBOX_URL)
    toolbox_tools = toolbox.load_toolset("tickets_toolset")
except Exception as e:
    print(f"Warning: Could not initialize Toolbox tools: {e}")
    toolbox_tools = []

# MCP Tools for GitHub operations
GITHUB_TOKEN = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
github_headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}

# Analysis tools (read-only) with serialization wrapper
try:
    mcp_tools_analyse_raw = MCPToolset(
        connection_params=StreamableHTTPConnectionParams(
            url="https://api.githubcopilot.com/mcp/",
            headers=github_headers,
        ),
        tool_filter=[
            "get_file_contents",
            "get_commit",
            "search_issues",
            "list_issues",
            "get_issue",
            "search_repositories",
            "list_pull_requests",
            "get_pull_request",
        ],
    )
    mcp_tools_analyse = SerializableMCPToolset(mcp_tools_analyse_raw)
except Exception as e:
    print(f"Warning: Could not initialize MCP analysis tools: {e}")
    mcp_tools_analyse = None

# PR and code modification tools with serialization wrapper
try:
    mcp_tools_pr_raw = MCPToolset(
        connection_params=StreamableHTTPConnectionParams(
            url="https://api.githubcopilot.com/mcp/",
            headers=github_headers,
        ),
        tool_filter=[
            "create_pull_request",
            "update_pull_request",
            "create_branch",
            "create_or_update_file",
            "delete_file",
            "list_branches",
            "push_files",
            "create_pull_request_with_copilot",
            "get_pull_request"
        ],
    )
    mcp_tools_pr = SerializableMCPToolset(mcp_tools_pr_raw)
except Exception as e:
    print(f"Warning: Could not initialize MCP PR tools: {e}")
    mcp_tools_pr = None

# ----- Specialized Agent Tools -----

# 1. Analysis Agent Tool
analysis_tools = [search_tool, get_current_date]
if stackoverflow_tool:
    analysis_tools.append(stackoverflow_tool)
if mcp_tools_analyse:
    analysis_tools.append(mcp_tools_analyse)

analysis_agent = Agent(
    model="gemini-2.5-flash",
    name="code_analysis_agent",
    instruction="""
    You are a senior software engineer specializing in code analysis and bug investigation.
    
    Your responsibilities:
    1. Analyze error logs and stack traces to identify root causes
    2. Examine relevant code files to understand the context
    3. Search for similar issues and solutions online
    4. Create comprehensive bug reports with:
       - Clear problem description
       - Root cause analysis
       - Impact assessment
       - Suggested solution approach
       - Relevant code snippets
    
    Use the available tools to:
    - Get file contents from repositories
    - Search for similar issues
    - Look up solutions on StackOverflow
    - Research best practices
    
    Always provide detailed, actionable analysis in JSON-serializable format.
    When working with URLs or complex objects, ensure they are converted to strings.
    """,
    tools=analysis_tools,
)
analysis_agent_tool = AgentTool(analysis_agent)

# 2. JIRA Agent Tool
jira_tools = toolbox_tools + [get_current_date]

jira_agent = Agent(
    model="gemini-2.5-flash",
    name="jira_management_agent",
    instruction="""
    You are a project management specialist responsible for JIRA ticket operations.
    
    Your responsibilities:
    1. Create detailed JIRA tickets from bug reports
    2. Update existing tickets with new information
    3. Link tickets with PR requests
    4. Maintain proper ticket status and workflow
    
    When creating tickets, include:
    - Clear, descriptive title
    - Detailed description with bug analysis
    - Priority and severity levels
    - Labels and components
    - Acceptance criteria
    
    When updating tickets:
    - Add PR links and details
    - Update status appropriately
    - Add relevant comments about progress
    
    Always ensure responses are in JSON-serializable format.
    """,
    tools=jira_tools,
)
jira_agent_tool = AgentTool(jira_agent)

# 3. Code Fixer Agent Tool
fixer_tools = [get_current_date]
if mcp_tools_pr:
    fixer_tools.append(mcp_tools_pr)
if mcp_tools_analyse:
    fixer_tools.append(mcp_tools_analyse)

code_fixer_agent = Agent(
    model="gemini-2.5-flash",
    name="code_fixer_agent",
    instruction="""
    You are an expert software developer specializing in bug fixes and code improvements.
    
    Your responsibilities:
    1. Implement bug fixes based on analysis reports
    2. Create new branches for fixes
    3. Make necessary code changes
    4. Create comprehensive pull requests
    5. Ensure code quality and best practices
    
    When fixing code:
    - Follow existing code style and patterns
    - Add appropriate comments and documentation
    - Include unit tests if applicable
    - Make minimal, targeted changes
    
    When creating PRs:
    - Write clear, descriptive titles
    - Include detailed descriptions with:
      - Problem description
      - Solution approach
      - Changes made
      - Testing notes
    - Link to related issues/tickets
    
    Always ensure responses are in JSON-serializable format.
    Convert any URL objects to strings before returning.
    """,
    tools=fixer_tools,
)
code_fixer_agent_tool = AgentTool(code_fixer_agent)