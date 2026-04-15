"""
CrewAI Adapter for AgentShrink Gateway + Sarvam AI
====================================================
Original: LLM(model="nebius/Qwen/Qwen3-235B-A22B", api_key=...)
Adapted:  LLM(model="openai/sarvam-m", api_base="http://127.0.0.1:8100/v1", api_key=...)

Works for: crewai_starter, agentic_rag_with_web_search, price_monitoring_agent,
           car_finder_agent, and any CrewAI-based agent
"""
import os
from crewai import Agent, Task, LLM, Crew, Process

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")


def create_sarvam_llm(model_id: str = "sarvam-m") -> LLM:
    return LLM(
        model=f"openai/{model_id}",
        api_base=GATEWAY_URL,
        api_key=GATEWAY_KEY,
    )


# --- Example: Adapt crewai_starter ---
# BEFORE:
#   llm=LLM(model="nebius/Qwen/Qwen3-235B-A22B", api_key=os.getenv("NEBIUS_API_KEY"))
#
# AFTER:
#   llm=create_sarvam_llm("sarvam-m")

if __name__ == "__main__":
    researcher = Agent(
        role="Senior Researcher",
        goal="Discover groundbreaking technologies",
        verbose=True,
        llm=create_sarvam_llm("sarvam-m"),
        backstory="A curious mind fascinated by cutting-edge innovation.",
    )

    research_task = Task(
        description="Identify the next big trend in AI",
        expected_output="5 paragraphs on the next big AI trend",
        agent=researcher,
    )

    crew = Crew(agents=[researcher], tasks=[research_task], process=Process.sequential)
    crew.kickoff()
