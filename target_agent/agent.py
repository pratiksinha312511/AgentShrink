"""
target_agent/agent.py
=====================
PHASE 0 — The Target Agent (Your Guinea Pig)

This is a customer support agent built deliberately badly —
it uses GPT-4o for EVERY single task, including trivial ones.

This is the agent AgentShrink will analyse and optimize.

WHY we build this first:
  AgentShrink needs a real agent to wrap around and test on.
  Without this, you have nothing to log, cluster, or replace.

The agent handles customer support queries with 5 nodes:
  1. classify    — "is this about refund, shipping, or product?"
  2. extract     — "what's the order ID in this message?"
  3. check_policy — "does this situation qualify for a refund?"
  4. draft_reply  — "write a professional reply to this customer"
  5. format_output — "format the reply as a JSON response"

Notice: tasks 1, 2, and 5 are SIMPLE. A tiny model could do them.
Tasks 3 and 4 are complex and genuinely need a strong model.
AgentShrink will discover this automatically.
"""

import os
from typing import TypedDict
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END

load_dotenv()


# ─────────────────────────────────────────────
# STATE SCHEMA
# This is the "memory" that flows between nodes.
# Each node reads from it and writes to it.
# ─────────────────────────────────────────────

class SupportState(TypedDict):
    customer_message: str       # The original customer message
    complaint_type: str         # "refund" | "shipping" | "product" | "other"
    order_id: str               # Extracted order ID (e.g., "ORD-12345")
    policy_verdict: str         # "approved" | "denied" | "needs_review"
    draft_reply: str            # The written reply to the customer
    final_response: dict        # Formatted JSON output


# ─────────────────────────────────────────────
# LLM SETUP
# We use a single ChatOpenAI instance.
# AgentShrink will later replace this with ShrinkLLM.
#
# NOTE: We pass a callbacks parameter — this is WHERE
# AgentShrinkLogger will hook in. For now it's empty.
# In Phase 1, you'll add: callbacks=[AgentShrinkLogger()]
# ─────────────────────────────────────────────

def _target_agent_provider() -> str:
    """Return which backend the demo agent should use."""
    return os.getenv("TARGET_AGENT_PROVIDER", "openai").strip().lower()


def _target_agent_model(provider: str) -> str:
    """Pick the configured model name for the selected provider."""
    if provider in {"ollama", "shrink"}:
        return os.getenv("TARGET_AGENT_OLLAMA_MODEL", "llama3.2:3b")
    if provider == "nvidia":
        return os.getenv("TARGET_AGENT_NVIDIA_MODEL", "moonshotai/kimi-k2-instruct")
    if provider == "gemini":
        return os.getenv("TARGET_AGENT_GEMINI_MODEL", "gemini-2.0-flash-lite")
    return os.getenv("TARGET_AGENT_OPENAI_MODEL", "gpt-4o-mini")


def get_llm(callbacks=None):
    """
    Returns the LLM instance.
    Accepts optional callbacks — this is the hook for AgentShrinkLogger.
    When callbacks=None, the agent runs normally with no logging.
    When callbacks=[AgentShrinkLogger()], every call gets captured.
    """
    provider = _target_agent_provider()
    model = _target_agent_model(provider)
    temperature = float(os.getenv("TARGET_AGENT_TEMPERATURE", "0"))
    callbacks = callbacks or []

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model,
            temperature=temperature,
            callbacks=callbacks,
            base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        )

    if provider == "shrink":
        from agentshrink import ShrinkLLM

        return ShrinkLLM(
            output_dir=os.getenv("AGENTSHRINK_OUTPUT_DIR", ".agentshrink_output"),
            fallback_provider=os.getenv("SHRINKLLM_FALLBACK_PROVIDER", "ollama"),
            fallback_model=os.getenv("SHRINKLLM_FALLBACK_MODEL", model),
            confidence_threshold=float(os.getenv("AGENTSHRINK_CONFIDENCE_THRESHOLD", "0.75")),
            temperature=temperature,
            trace_mode=os.getenv("SHRINKLLM_TRACE_MODE", "1") == "1",
            callbacks=callbacks,
        )

    if provider == "openai":
        base_url = os.getenv("OPENAI_BASE_URL", None)
        api_key = os.getenv("OPENAI_API_KEY", None)
        kwargs = {}
        if base_url:
            kwargs["base_url"] = base_url
        if api_key:
            kwargs["api_key"] = api_key
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            callbacks=callbacks,
            **kwargs,
        )

    if provider == "nvidia":
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            callbacks=callbacks,
            base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            api_key=os.getenv("NVIDIA_API_KEY"),
        )

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            callbacks=callbacks,
        )

    raise ValueError(
        f"Unsupported TARGET_AGENT_PROVIDER='{provider}'. "
        "Use 'openai', 'nvidia', 'gemini', 'ollama', or 'shrink'."
    )


# ─────────────────────────────────────────────
# NODE 1: CLASSIFY
# Task: Determine what type of complaint this is.
# Reality check: A 2B model can do this perfectly.
# GPT-4o-mini is massive overkill here.
# ─────────────────────────────────────────────

def classify_node(state: SupportState, callbacks=None) -> SupportState:
    """
    Classifies the customer complaint into a category.

    This is a SIMPLE classification task.
    The prompt is always the same template.
    The output is always one of 4 words.
    A fine-tuned 2B model will handle this at 95%+ accuracy.
    """
    llm = get_llm(callbacks)

    messages = [
        SystemMessage(content="""You are a customer support classifier.
Classify the customer message into exactly one category.
Respond with ONLY one word: refund, shipping, product, or other.
No explanation. No punctuation. Just the category word."""),
        HumanMessage(content=f"Customer message: {state['customer_message']}")
    ]

    response = llm.invoke(messages)
    complaint_type = response.content.strip().lower()

    # Validate — if LLM goes off-script, default to "other"
    valid_types = {"refund", "shipping", "product", "other"}
    if complaint_type not in valid_types:
        complaint_type = "other"

    return {**state, "complaint_type": complaint_type}


# ─────────────────────────────────────────────
# NODE 2: EXTRACT ORDER ID
# Task: Find the order ID in the customer's message.
# Reality check: Pure entity extraction. Regex could do this.
# A 2B model handles it easily. GPT-4o is 100x overkill.
# ─────────────────────────────────────────────

def extract_node(state: SupportState, callbacks=None) -> SupportState:
    """
    Extracts the order ID from the customer message.

    This is a simple NER (named entity recognition) task.
    Order IDs follow patterns like ORD-12345, #12345, Order 12345.
    This is the perfect example of a task that should be replaced.
    """
    llm = get_llm(callbacks)

    messages = [
        SystemMessage(content="""You are an order ID extractor.
Extract the order ID from the customer message.
If found, respond with ONLY the order ID (e.g., ORD-12345).
If not found, respond with ONLY the word: NOT_FOUND.
No explanation. No extra text."""),
        HumanMessage(content=f"Customer message: {state['customer_message']}")
    ]

    response = llm.invoke(messages)
    order_id = response.content.strip()

    return {**state, "order_id": order_id}


# ─────────────────────────────────────────────
# NODE 3: CHECK POLICY
# Task: Based on complaint type and context, determine if
#       a refund/resolution is warranted.
# Reality check: This requires REASONING. The model needs to
# apply multiple business rules and edge cases.
# This is a task that genuinely benefits from a stronger model.
# ─────────────────────────────────────────────

def check_policy_node(state: SupportState, callbacks=None) -> SupportState:
    """
    Applies business rules to determine the resolution.

    This is a COMPLEX reasoning task.
    It needs to understand context, exceptions, edge cases.
    This should STAY on GPT-4o after AgentShrink runs —
    and AgentShrink should correctly identify this.
    """
    llm = get_llm(callbacks)

    policy_rules = """
    REFUND POLICY:
    - Products damaged in shipping: ALWAYS approved
    - Wrong item received: ALWAYS approved
    - Changed mind (within 7 days): approved
    - Changed mind (after 7 days): denied
    - Digital products: denied (no refunds on digital goods)
    - Items marked final sale: denied

    SHIPPING POLICY:
    - Delayed beyond 14 days: approved for reship or refund
    - Delayed within 14 days: needs_review (still in transit)
    - Lost in transit (carrier confirmed): approved
    """

    messages = [
        SystemMessage(content=f"""You are a customer support policy checker.
Apply these policies to the customer situation:

{policy_rules}

Respond with ONLY one word: approved, denied, or needs_review."""),
        HumanMessage(content=f"""
Complaint type: {state['complaint_type']}
Order ID: {state['order_id']}
Customer message: {state['customer_message']}
""")
    ]

    response = llm.invoke(messages)
    verdict = response.content.strip().lower()

    valid_verdicts = {"approved", "denied", "needs_review"}
    if verdict not in valid_verdicts:
        verdict = "needs_review"

    return {**state, "policy_verdict": verdict}


# ─────────────────────────────────────────────
# NODE 4: DRAFT REPLY
# Task: Write a professional, empathetic reply to the customer.
# Reality check: This is the MOST complex task.
# It needs to be empathetic, accurate, on-brand, and clear.
# This should absolutely stay on GPT-4o.
# ─────────────────────────────────────────────

def draft_reply_node(state: SupportState, callbacks=None) -> SupportState:
    """
    Writes the actual customer reply.

    This is where language quality matters most.
    The customer will READ this. It needs to be warm, clear,
    professionally written, and correctly reflect the resolution.
    This is one task that should NOT be replaced with a tiny model.
    """
    llm = get_llm(callbacks)

    verdict_instructions = {
        "approved": "Tell the customer their request has been approved. Be warm and reassuring. Explain next steps clearly.",
        "denied": "Explain the denial respectfully and empathetically. Offer alternatives if possible. Don't be cold.",
        "needs_review": "Tell the customer their case needs more investigation. Give a clear timeline (24-48 hours). Be reassuring."
    }

    instruction = verdict_instructions.get(
        state["policy_verdict"],
        "Respond professionally and helpfully."
    )

    messages = [
        SystemMessage(content=f"""You are a professional customer support agent.
Write a reply to the customer.
{instruction}
Keep it under 100 words. Be warm but professional."""),
        HumanMessage(content=f"""
Customer message: {state['customer_message']}
Order ID: {state['order_id']}
Resolution: {state['policy_verdict']}
""")
    ]

    response = llm.invoke(messages)
    return {**state, "draft_reply": response.content.strip()}


# ─────────────────────────────────────────────
# NODE 5: FORMAT OUTPUT
# Task: Convert the draft reply into a structured JSON response.
# Reality check: Pure text formatting task.
# Always the same template. A 2B model nails this.
# ─────────────────────────────────────────────

def format_output_node(state: SupportState, callbacks=None) -> SupportState:
    """
    Formats everything into a final JSON structure.

    This is a SIMPLE formatting task.
    The template never changes. The output is always the same structure.
    Classic example of "using a Ferrari to drive to the corner shop."
    After AgentShrink: this will route to Gemma 2B at 95%+ quality.
    """
    llm = get_llm(callbacks)

    messages = [
        SystemMessage(content="""You are a JSON formatter.
Convert the support response into this exact JSON structure.
Respond with ONLY valid JSON — no markdown, no code blocks, just JSON:
{
  "order_id": "...",
  "complaint_type": "...",
  "resolution": "...",
  "reply": "...",
  "escalate": true/false
}
Set escalate to true if resolution is needs_review, false otherwise."""),
        HumanMessage(content=f"""
order_id: {state['order_id']}
complaint_type: {state['complaint_type']}
resolution: {state['policy_verdict']}
reply: {state['draft_reply']}
""")
    ]

    response = llm.invoke(messages)

    # Parse the JSON response safely
    import json
    try:
        formatted = json.loads(response.content.strip())
    except json.JSONDecodeError:
        # If LLM doesn't return valid JSON (it happens), build it manually
        formatted = {
            "order_id": state["order_id"],
            "complaint_type": state["complaint_type"],
            "resolution": state["policy_verdict"],
            "reply": state["draft_reply"],
            "escalate": state["policy_verdict"] == "needs_review"
        }

    return {**state, "final_response": formatted}


# ─────────────────────────────────────────────
# BUILD THE GRAPH
# LangGraph wires the nodes together.
# Flow: classify → extract → check_policy → draft_reply → format_output
# ─────────────────────────────────────────────

def build_agent(callbacks=None):
    """
    Builds and compiles the LangGraph agent.

    The callbacks parameter flows through to every LLM call.
    This is the hook that AgentShrinkLogger will use in Phase 1.

    Usage:
        agent = build_agent()                              # no logging
        agent = build_agent(callbacks=[logger])            # with logging
        result = agent.invoke({"customer_message": "..."})
    """

    def classify(state):     return classify_node(state, callbacks)
    def extract(state):      return extract_node(state, callbacks)
    def check_policy(state): return check_policy_node(state, callbacks)
    def draft_reply(state):  return draft_reply_node(state, callbacks)
    def format_out(state):   return format_output_node(state, callbacks)

    graph = StateGraph(SupportState)

    # Add all nodes
    graph.add_node("classify_node",      classify)
    graph.add_node("extract_node",       extract)
    graph.add_node("check_policy_node",  check_policy)
    graph.add_node("draft_reply_node",   draft_reply)
    graph.add_node("format_output_node", format_out)

    # Wire them in sequence
    graph.add_edge(START,                 "classify_node")
    graph.add_edge("classify_node",       "extract_node")
    graph.add_edge("extract_node",        "check_policy_node")
    graph.add_edge("check_policy_node",   "draft_reply_node")
    graph.add_edge("draft_reply_node",    "format_output_node")
    graph.add_edge("format_output_node",  END)

    return graph.compile()


# ─────────────────────────────────────────────
# TEST DATA
# 8 diverse customer messages covering all complaint types.
# Run these to generate logged data in Phase 1.
# ─────────────────────────────────────────────

TEST_MESSAGES = [
    # Refund scenarios
    "Hi, I received the wrong item. I ordered a blue shirt (ORD-10021) but got a red one. I want a refund please.",
    "My order ORD-10034 was damaged when it arrived. The box was crushed and the item inside was broken. Need refund.",
    "I changed my mind about my purchase from last week, order number ORD-10089. Can I return it?",
    "I bought a digital download ORD-10102 but I don't like it. Can I get my money back?",

    # Shipping scenarios
    "My package ORD-10045 was supposed to arrive 20 days ago and still hasn't come. Where is it?",
    "Order ORD-10067 shows delivered but I never received it. The carrier says it was left at the door.",

    # Product scenarios
    "The laptop I bought (order ORD-10078) stopped working after 2 days. Screen just went black.",
    "ORD-10091 arrived but the product is completely different from what was shown on the website.",
]


# ─────────────────────────────────────────────
# MAIN — Run this file directly to test the agent
# ─────────────────────────────────────────────

if __name__ == "__main__":
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    import json

    console = Console()
    provider = _target_agent_provider()
    model = _target_agent_model(provider)

    console.print(Panel.fit(
        "[bold]Phase 0 — Target Agent Test[/bold]\n"
        "Running 3 test messages through the agent.\n"
        f"Provider: {provider} ({model})\n"
        "Every call uses the same model — even the simple ones.\n"
        "This is what AgentShrink will fix.",
        border_style="yellow"
    ))

    agent = build_agent()  # No callbacks yet — pure GPT-4o

    for i, message in enumerate(TEST_MESSAGES[:3], 1):
        console.print(f"\n[bold yellow]Test {i}/3[/bold yellow]")
        console.print(f"[dim]Message:[/dim] {message[:60]}...")

        result = agent.invoke({
            "customer_message": message,
            "complaint_type": "",
            "order_id": "",
            "policy_verdict": "",
            "draft_reply": "",
            "final_response": {}
        })

        # Display results in a table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="dim", width=18)
        table.add_column("Value", style="white")

        table.add_row("Complaint type", result["complaint_type"])
        table.add_row("Order ID",       result["order_id"])
        table.add_row("Verdict",        result["policy_verdict"])
        table.add_row("Reply preview",  result["draft_reply"][:80] + "...")

        console.print(table)

    console.print(Panel.fit(
        "[bold green]✓ Agent working correctly[/bold green]\n"
        "5 GPT-4o calls per message × 3 messages = 15 total API calls.\n"
        "At least 9 of those calls were unnecessary (classify, extract, format).\n"
        "AgentShrink will find and fix this in Phase 1-4.",
        border_style="green"
    ))
