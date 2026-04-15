"""
LlamaIndex Adapter for AgentShrink Gateway + Sarvam AI
=======================================================
Original: NebiusLLM(model="Qwen/Qwen3-235B-A22B", api_key=...)
Adapted:  OpenAILike(model="sarvam-m", api_base="http://127.0.0.1:8100/v1", api_key=...)

Works for: llamaindex_starter, llamaIndex_starter (RAG)
"""
import os
from llama_index.llms.openai_like import OpenAILike

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")


def create_sarvam_llm(model_id: str = "sarvam-m") -> OpenAILike:
    return OpenAILike(
        model=model_id,
        api_base=GATEWAY_URL,
        api_key=GATEWAY_KEY,
        is_chat_model=True,
    )


# --- Example: Adapt llamaindex_starter ---
# BEFORE:
#   from llama_index.llms.nebius import NebiusLLM
#   llm=NebiusLLM(model="Qwen/Qwen3-235B-A22B", api_key=os.getenv("NEBIUS_API_KEY"))
#
# AFTER:
#   from llama_index.llms.openai_like import OpenAILike
#   llm=create_sarvam_llm("sarvam-m")

if __name__ == "__main__":
    llm = create_sarvam_llm("sarvam-m")
    response = llm.complete("What is AgentShrink?")
    print(response.text)
