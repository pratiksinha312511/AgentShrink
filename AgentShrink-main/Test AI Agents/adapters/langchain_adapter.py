"""
LangChain / LangGraph Adapter for AgentShrink + Sarvam AI
==========================================================
Two methods available:

Method 1 (ShrinkLLM — full routing): Replace ChatOpenAI with ShrinkLLM
Method 2 (Gateway — base_url swap): Change ChatOpenAI base_url to gateway

Works for: langchain_langgraph_starter, talk_to_db, browser_agent,
           study_coach_agent, langchain_langgraph_mcp_agent
"""
import os

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")


# ─── METHOD 1: ShrinkLLM (recommended for full routing) ───
def create_shrinkllm():
    from agentshrink import ShrinkLLM
    return ShrinkLLM(output_dir=".agentshrink_output")


# ─── METHOD 2: Gateway proxy (simpler, just base_url change) ───
def create_gateway_chat(model_id: str = "sarvam-m"):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=model_id,
        base_url=GATEWAY_URL,
        api_key=GATEWAY_KEY,
    )


# --- Example: Adapt langchain_langgraph_starter ---
# BEFORE:
#   from langchain_openai import ChatOpenAI
#   llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))
#
# AFTER (Method 1 — ShrinkLLM):
#   from agentshrink import ShrinkLLM
#   llm = ShrinkLLM(output_dir=".agentshrink_output")
#
# AFTER (Method 2 — Gateway):
#   llm = ChatOpenAI(model="sarvam-m",
#                    base_url="http://127.0.0.1:8100/v1",
#                    api_key="project-token")

if __name__ == "__main__":
    # Using Gateway method
    llm = create_gateway_chat("sarvam-m")
    response = llm.invoke("What is AgentShrink?")
    print(response.content)
