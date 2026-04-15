"""
DSPy Agent — Adapted for AgentShrink Gateway + Sarvam AI
Original: awesome-ai-apps/starter_ai_agents/dspy_starter/main.py
"""
import os
import dspy

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")

lm = dspy.LM(
    "openai/sarvam-m",
    api_key=GATEWAY_KEY,
    api_base=GATEWAY_URL,
)
dspy.configure(lm=lm)


def evaluate_math(expression: str):
    return dspy.PythonInterpreter({}).execute(expression)


def search_wikipedia(query: str):
    results = dspy.ColBERTv2(url="http://20.102.90.50:2017/wiki17_abstracts")(query, k=3)
    return [x["text"] for x in results]


react = dspy.ReAct("question -> answer: str", tools=[evaluate_math, search_wikipedia])

if __name__ == "__main__":
    question = "What is 9362158 divided by the year of Messi's first Ballon d'Or?"
    pred = react(question=question)
    print("Question:", question)
    print("Answer:", pred.answer)
