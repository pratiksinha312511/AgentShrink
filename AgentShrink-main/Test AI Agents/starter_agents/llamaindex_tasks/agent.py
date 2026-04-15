"""
LlamaIndex Task Manager — Adapted for AgentShrink Gateway + Sarvam AI
Original: awesome-ai-apps/starter_ai_agents/llamaindex_starter/main.py
"""
import os
from llama_index.core.tools import FunctionTool
from llama_index.core.agent import ReActAgent
from llama_index.llms.openai_like import OpenAILike
from datetime import datetime

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")


def calculate_task_duration(start_time: str, end_time: str) -> str:
    """Calculate the duration between two times in HH:MM format"""
    try:
        start = datetime.strptime(start_time, "%H:%M")
        end = datetime.strptime(end_time, "%H:%M")
        duration = end - start
        hours = duration.seconds // 3600
        minutes = (duration.seconds % 3600) // 60
        return f"{hours} hours and {minutes} minutes"
    except ValueError:
        return "Invalid time format. Please use HH:MM format."


def estimate_task_completion(tasks: int, time_per_task: int) -> str:
    """Estimate total time needed to complete a number of tasks"""
    total_minutes = tasks * time_per_task
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours} hours and {minutes} minutes"


def calculate_productivity(tasks_completed: int, total_time: int) -> str:
    """Calculate tasks completed per hour"""
    if total_time <= 0:
        return "Cannot calculate productivity with zero or negative time"
    hours = total_time / 60
    tasks_per_hour = tasks_completed / hours
    return f"{tasks_per_hour:.2f} tasks per hour"


duration_tool = FunctionTool.from_defaults(fn=calculate_task_duration)
estimate_tool = FunctionTool.from_defaults(fn=estimate_task_completion)
productivity_tool = FunctionTool.from_defaults(fn=calculate_productivity)

agent = ReActAgent.from_tools(
    [duration_tool, estimate_tool, productivity_tool],
    llm=OpenAILike(
        model="sarvam-m",
        api_base=GATEWAY_URL,
        api_key=GATEWAY_KEY,
        is_chat_model=True,
    ),
    verbose=True,
)

if __name__ == "__main__":
    print("\nTask Management Assistant (AgentShrink + Sarvam AI)")
    response = agent.chat("If I worked from 09:00 to 17:00 and completed 8 tasks, what was my productivity rate?")
    print("\nResponse:", response)
