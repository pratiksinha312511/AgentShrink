"""
LangGraph MCP Agent — Adapted for AgentShrink Gateway + Sarvam AI
Original: awesome-ai-apps/mcp_ai_agents/langchain_langgraph_mcp_agent
"""
import os
from langchain_openai import ChatOpenAI
# from agentshrink import ShrinkLLM  # Alternative: full ShrinkLLM routing

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")

llm = ChatOpenAI(model="sarvam-m", base_url=GATEWAY_URL, api_key=GATEWAY_KEY)

if __name__ == "__main__":
    response = llm.invoke("Search this documentation for information about authentication setup")
    print(response.content)
