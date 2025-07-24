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

# New imports for context retrieval
from google.cloud import aiplatform
from langchain_google_vertexai import VertexAIEmbeddings, ChatVertexAI
from langchain_pinecone import Pinecone as LangchainPinecone
from pinecone import Pinecone

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ----- Context Retrieval Configuration -----
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "developer1-quickstart-py")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "springboot-java")

# ---- ENVIRONMENT SETUP ----
os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
aiplatform.init(project=PROJECT_ID, location=LOCATION)

class VectorDatabaseManager:
    """Manages vector database operations for code context retrieval"""
    
    def __init__(self, project_id, location, pinecone_api_key, pinecone_index_name, pinecone_namespace):
        self.project_id = project_id
        self.location = location
        self.pinecone_api_key = pinecone_api_key
        self.pinecone_index_name = pinecone_index_name
        self.pinecone_namespace = pinecone_namespace
        
        # Initialize embedding model
        self.embed_model = VertexAIEmbeddings(
            model_name="text-embedding-005",
            project=project_id,
            location=location
        )
        
        # Connect to existing Pinecone index
        self.pc = Pinecone(api_key=pinecone_api_key)
        self.index = self.pc.Index(name=pinecone_index_name)
        
        # Create vectorstore for retrieval
        self.vectorstore = LangchainPinecone(
            index=self.index,
            embedding=self.embed_model,
            namespace=pinecone_namespace,
            text_key="text"
        )
        
        self.retriever = self.vectorstore.as_retriever(
            search_type="similarity", 
            search_kwargs={"k": 5}
        )
    
    def retrieve_relevant_code(self, query, k=5):
        """Retrieve relevant code snippets from existing vectorstore"""
        try:
            custom_retriever = self.vectorstore.as_retriever(
                search_type="similarity", 
                search_kwargs={"k": k}
            )
            
            docs = custom_retriever.get_relevant_documents(query)
            
            if not docs:
                return {
                    "success": True,
                    "retrieved_code": "// No relevant code found.",
                    "sources": [],
                    "num_documents": 0
                }
            
            retrieved_code = ""
            sources = []
            seen_sources = set()
            
            for doc in docs:
                source = doc.metadata.get("source", "unknown")
                if source in seen_sources:
                    continue
                    
                seen_sources.add(source)
                code = doc.metadata.get("text", doc.page_content).strip()
                retrieved_code += f"// From: {source}\n{code}\n\n"
                sources.append(source)
            
            return {
                "success": True,
                "retrieved_code": retrieved_code,
                "sources": sources,
                "num_documents": len(docs)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "retrieved_code": "// Error accessing vectorstore.",
                "sources": [],
                "num_documents": 0
            }

# Initialize context retriever
context_retriever = VectorDatabaseManager(
    project_id=PROJECT_ID,
    location=LOCATION,
    pinecone_api_key=PINECONE_API_KEY,
    pinecone_index_name=PINECONE_INDEX_NAME,
    pinecone_namespace=PINECONE_NAMESPACE
)

# ----- Utility Functions -----
def get_current_date() -> dict:
    """Get the current date in the format YYYY-MM-DD"""
    return {"current_date": datetime.now().strftime("%Y-%m-%d")}

def retrieve_code_context(query: str, max_results: int = 5) -> dict:
    """Tool function to retrieve relevant code context from vector database"""
    try:
        relevant_code = context_retriever.retrieve_relevant_code(query, k=max_results)
        return {
            "query": query,
            "relevant_code_context": relevant_code,
            "status": "success"
        }
    except Exception as e:
        return {
            "query": query,
            "relevant_code_context": f"// Error: {str(e)}",
            "status": "error",
            "error": str(e)
        }

def retrieve_code_context(query: str, max_results: int = 5) -> dict:
    """Tool function to retrieve relevant code context from vector database"""
    try:
        relevant_code = context_retriever.retrieve_relevant_code(query, k=max_results)
        return {
            "query": query,
            "relevant_code_context": relevant_code,
            "status": "success"
        }
    except Exception as e:
        return {
            "query": query,
            "relevant_code_context": f"// Error: {str(e)}",
            "status": "error",
            "error": str(e)
        }

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
        "search_repositories"
    ],
)

# ----- Specialized Agent Tools -----

# 1. Enhanced Analysis Agent Tool with Context Retrieval
analysis_agent = Agent(
    model="gemini-2.5-flash",
    name="code_analysis_agent",
    instruction="""
    You are a senior software engineer specializing in code analysis and bug investigation with access to a comprehensive codebase context database.
    
    Your responsibilities:
    1. Analyze error logs and stack traces to identify root causes
    2. Use the retrieve_code_context tool to get relevant code snippets from the vector database
    3. Examine relevant code files to understand the context
    4. Search for similar issues and solutions online
    5. Create comprehensive bug reports with:
       - Clear problem description
       - Root cause analysis based on retrieved code context
       - Impact assessment
       - Suggested solution approach
       - Relevant code snippets from the codebase
    
    Use the available tools in this order:
    1. First, use retrieve_code_context with the error message or exception to get relevant code
    2. Analyze the retrieved code context to understand the problem
    3. Use other tools (GitHub, search, StackOverflow) for additional context
    4. Provide detailed, actionable analysis
    
    When using retrieve_code_context:
    - Pass the full error message or exception as the query
    - Review the returned code context carefully
    - Use it to understand the codebase structure and identify the root cause
    
    Always provide detailed, actionable analysis with specific code references.
    """,
    tools=[retrieve_code_context, search_tool, stackoverflow_tool, mcp_tools_analyse, get_current_date],
)
analysis_agent_tool = AgentTool(analysis_agent)

# 2. JIRA Agent Tool (unchanged)
jira_agent = Agent(
    model="gemini-2.5-flash",
    name="jira_management_agent",
    instruction="""
    You are a project management specialist responsible for JIRA ticket operations.
    
    Your responsibilities:
    1. Create detailed JIRA tickets from bug reports
    2. Update existing tickets with new information
    3. Maintain proper ticket status and workflow
    
    When creating tickets, include:
    - Clear, descriptive title
    - Detailed description with bug analysis
    - Priority and severity levels
    - Labels and components
    - Acceptance criteria
    
    When updating tickets:
    - Add relevant details
    - Update status appropriately
    - Add relevant comments about progress
    """,
    tools=toolbox_tools + [get_current_date],
)
jira_agent_tool = AgentTool(jira_agent)

# 3. Enhanced Code Fixer Agent Tool with Context Retrieval
code_fixer_agent = Agent(
    model="gemini-2.5-flash",
    name="code_fixer_agent",
    instruction="""
    You are an expert software developer specializing in bug fixes and code improvements with access to a comprehensive codebase context database.
    
    Your responsibilities:
    1. Use retrieve_code_context to get relevant code snippets for the bug/issue
    2. Implement bug fixes based on analysis reports and retrieved context
    3. Follow existing code patterns and styles from the retrieved context
    4. Make necessary code changes
    5. Create comprehensive pull requests suggestions
    6. Ensure code quality and best practices
    
    Workflow for fixing bugs:
    1. First, use retrieve_code_context with the error/issue description to get relevant code
    2. Analyze the retrieved code context to understand the current implementation
    3. Implement the fix following the existing code patterns from the retrieved context
    4. Create PR suggestion for with detailed description including context analysis
    
    When fixing code:
    - Use the retrieved code context to understand existing patterns and styles
    - Follow existing code style and patterns from the codebase
    - Add appropriate comments and documentation
    - Make minimal, targeted changes
    - Reference the retrieved code context in your implementation decisions

    When creating PR suggestions:
    - Write clear, descriptive titles
    - Include detailed descriptions with:
      - Problem description
      - Analysis based on retrieved code context
      - Solution approach
      - Changes made
      - Testing notes
    - Update related issues/tickets with PR information
    """,
    tools=[retrieve_code_context, mcp_tools_analyse, get_current_date],
)
code_fixer_agent_tool = AgentTool(code_fixer_agent)

