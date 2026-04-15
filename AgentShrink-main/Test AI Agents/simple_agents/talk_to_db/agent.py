"""
LangChain Talk-to-DB Agent — Adapted for AgentShrink Gateway + Sarvam AI
Original: awesome-ai-apps/simple_ai_agents/talk_to_db/main.py
"""
import os
from langchain_openai import ChatOpenAI
# Alternative: from agentshrink import ShrinkLLM

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "project-token")

# Method 1: Gateway proxy
llm = ChatOpenAI(
    model="sarvam-m",
    base_url=GATEWAY_URL,
    api_key=GATEWAY_KEY,
)

# Method 2: ShrinkLLM (uncomment to use full routing)
# from agentshrink import ShrinkLLM
# llm = ShrinkLLM(output_dir=".agentshrink_output")

if __name__ == "__main__":
    response = llm.invoke("Write a SQL query to find the top 10 customers by order count")
    print(response.content)
