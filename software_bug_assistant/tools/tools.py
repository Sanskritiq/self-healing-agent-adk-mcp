from datetime import datetime
import os
import json

from google.adk.agents import Agent
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.langchain_tool import LangchainTool
from google.adk.tools.mcp_tool import MCPToolset, StreamableHTTPConnectionParams
from langchain_community.tools import StackExchangeTool
from langchain_community.utilities import StackExchangeAPIWrapper
from toolbox_core import ToolboxSyncClient

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ----- Utility Function -----
def get_current_date() -> dict:
    """Get the current date in the format YYYY-MM-DD"""
    return {"current_date": datetime.now().strftime("%Y-%m-%d")}

# ----- Initialize Base Tools -----

# Search Agent for web searches
search_agent = Agent(
    model="gemini-2.5-flash",
    name="search_agent",
    instruction="""
    You're a specialist in Google Search. Focus on finding relevant technical documentation,
    bug reports, and solutions for programming issues. Provide concise, actionable information.
    """,
    tools=[google_search],
)
search_tool = AgentTool(search_agent)

# StackOverflow tool for technical Q&A
stack_exchange_tool = StackExchangeTool(api_wrapper=StackExchangeAPIWrapper())
stackoverflow_tool = LangchainTool(stack_exchange_tool)

# Toolbox for JIRA operations
TOOLBOX_URL = os.getenv("MCP_TOOLBOX_URL", "http://127.0.0.1:5000")
toolbox = ToolboxSyncClient(TOOLBOX_URL)
toolbox_tools = toolbox.load_toolset("tickets_toolset")

# MCP Tools for GitHub operations
GITHUB_TOKEN = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
github_headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}

# Analysis tools (read-only)
mcp_tools_analyse = MCPToolset(
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

# PR and code modification tools
mcp_tools_pr = MCPToolset(
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

# ----- Specialized Agent Tools -----

# 1. Analysis Agent Tool
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
    
    Always provide detailed, actionable analysis.
    """,
    tools=[search_tool, stackoverflow_tool, mcp_tools_analyse, get_current_date],
)
analysis_agent_tool = AgentTool(analysis_agent)

# 2. JIRA Agent Tool
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
    """,
    tools=toolbox_tools + [get_current_date],
)
jira_agent_tool = AgentTool(jira_agent)

# 3. Code Fixer Agent Tool
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
    """,
    tools=[mcp_tools_pr, mcp_tools_analyse, get_current_date],
)
code_fixer_agent_tool = AgentTool(code_fixer_agent)