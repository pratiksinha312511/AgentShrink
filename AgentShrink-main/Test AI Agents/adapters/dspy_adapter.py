"""
DSPy Adapter for AgentShrink Gateway + Sarvam AI
==================================================
Original: dspy.LM("nebius/...", api_base="https://api.tokenfactory.nebius.com/v1")
Adapted:  dspy.LM("openai/sarvam-m", api_base="http://127.0.0.1:8100/v1")

Works for: dspy_starter
"""
import os
import dspy

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")


def configure_sarvam(model_id: str = "sarvam-m"):
    lm = dspy.LM(
        f"openai/{model_id}",
        api_key=GATEWAY_KEY,
        api_base=GATEWAY_URL,
    )
    dspy.configure(lm=lm)
    return lm


# --- Example: Adapt dspy_starter ---
# BEFORE:
#   lm = dspy.LM("nebius/moonshotai/Kimi-K2-Instruct",
#                 api_key=os.environ.get("NEBIUS_API_KEY"),
#                 api_base="https://api.tokenfactory.nebius.com/v1")
#
# AFTER:
#   lm = configure_sarvam("sarvam-m")

if __name__ == "__main__":
    configure_sarvam("sarvam-m")
    predict = dspy.Predict("question -> answer")
    result = predict(question="What is AgentShrink?")
    print(result.answer)
