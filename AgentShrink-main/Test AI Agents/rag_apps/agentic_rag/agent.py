"""
RAG Application (Agno) — Adapted for AgentShrink Gateway + Sarvam AI
Original: awesome-ai-apps/rag_apps/agentic_rag
"""
import os
from agno.agent import Agent
from agno.models.openai import OpenAIChat

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")

agent = Agent(
    name="RAG Agent",
    model=OpenAIChat(id="sarvam-m", base_url=GATEWAY_URL, api_key=GATEWAY_KEY),
    instructions=["You are a retrieval-augmented AI that answers questions based on retrieved document context."],
    markdown=True,
)

if __name__ == "__main__":
    agent.print_response("Summarize the key findings from the uploaded research paper.")
