"""
Alternative target agent with a different workflow shape.

This gives us a second end-to-end demo so AgentShrink isn't tied only to the
original customer support graph.
"""

import json
import os
from typing import TypedDict

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from target_agent.agent import get_llm

load_dotenv()


class CaseState(TypedDict):
    customer_message: str
    intent_label: str
    account_id: str
    action_plan: str
    internal_note: str
    final_packet: dict


def intent_route_node(state: CaseState, callbacks=None) -> CaseState:
    llm = get_llm(callbacks)
    messages = [
        SystemMessage(content="""You classify support operations messages.
Respond with exactly one word: cancel, refund, address, status, warranty, or other."""),
        HumanMessage(content=f"Message: {state['customer_message']}"),
    ]
    response = llm.invoke(messages)
    label = response.content.strip().lower()
    valid = {"cancel", "refund", "address", "status", "warranty", "other"}
    if label not in valid:
        label = "other"
    return {**state, "intent_label": label}


def extract_case_fields_node(state: CaseState, callbacks=None) -> CaseState:
    llm = get_llm(callbacks)
    messages = [
        SystemMessage(content="""Extract the customer account or order reference.
If present, respond with only the identifier.
If not found, respond with ONLY NOT_FOUND."""),
        HumanMessage(content=f"Message: {state['customer_message']}"),
    ]
    response = llm.invoke(messages)
    return {**state, "account_id": response.content.strip()}


def decide_resolution_node(state: CaseState, callbacks=None) -> CaseState:
    llm = get_llm(callbacks)
    messages = [
        SystemMessage(content="""You are an operations policy planner.
Decide the next action for this support case.

Rules:
- cancel before shipment -> cancel_now
- refund for damaged or wrong item -> refund_now
- address change before shipment -> update_address
- delivery delay beyond 14 days -> investigate_shipping
- warranty issue within 30 days -> replace_or_refund

Respond with exactly one phrase:
cancel_now, refund_now, update_address, investigate_shipping, replace_or_refund, or manual_review."""),
        HumanMessage(content=f"""
Intent: {state['intent_label']}
Identifier: {state['account_id']}
Message: {state['customer_message']}
"""),
    ]
    response = llm.invoke(messages)
    plan = response.content.strip().lower()
    valid = {
        "cancel_now",
        "refund_now",
        "update_address",
        "investigate_shipping",
        "replace_or_refund",
        "manual_review",
    }
    if plan not in valid:
        plan = "manual_review"
    return {**state, "action_plan": plan}


def compose_internal_note_node(state: CaseState, callbacks=None) -> CaseState:
    llm = get_llm(callbacks)
    messages = [
        SystemMessage(content="""Write a brief internal operations note for a support teammate.
Keep it under 60 words and include the recommended action."""),
        HumanMessage(content=f"""
Customer message: {state['customer_message']}
Intent: {state['intent_label']}
Identifier: {state['account_id']}
Action plan: {state['action_plan']}
"""),
    ]
    response = llm.invoke(messages)
    return {**state, "internal_note": response.content.strip()}


def package_case_node(state: CaseState, callbacks=None) -> CaseState:
    llm = get_llm(callbacks)
    messages = [
        SystemMessage(content="""Format the case summary as valid JSON only:
{
  "intent": "...",
  "identifier": "...",
  "action_plan": "...",
  "internal_note": "...",
  "requires_human": true/false
}
Set requires_human to true only for manual_review."""),
        HumanMessage(content=f"""
intent: {state['intent_label']}
identifier: {state['account_id']}
action_plan: {state['action_plan']}
internal_note: {state['internal_note']}
"""),
    ]
    response = llm.invoke(messages)
    try:
        packet = json.loads(response.content.strip())
    except json.JSONDecodeError:
        packet = {
            "intent": state["intent_label"],
            "identifier": state["account_id"],
            "action_plan": state["action_plan"],
            "internal_note": state["internal_note"],
            "requires_human": state["action_plan"] == "manual_review",
        }
    return {**state, "final_packet": packet}


def build_case_agent(callbacks=None):
    def route(state): return intent_route_node(state, callbacks)
    def extract(state): return extract_case_fields_node(state, callbacks)
    def decide(state): return decide_resolution_node(state, callbacks)
    def note(state): return compose_internal_note_node(state, callbacks)
    def package(state): return package_case_node(state, callbacks)

    graph = StateGraph(CaseState)
    graph.add_node("intent_route_node", route)
    graph.add_node("extract_case_fields_node", extract)
    graph.add_node("decide_resolution_node", decide)
    graph.add_node("compose_internal_note_node", note)
    graph.add_node("package_case_node", package)

    graph.add_edge(START, "intent_route_node")
    graph.add_edge("intent_route_node", "extract_case_fields_node")
    graph.add_edge("extract_case_fields_node", "decide_resolution_node")
    graph.add_edge("decide_resolution_node", "compose_internal_note_node")
    graph.add_edge("compose_internal_note_node", "package_case_node")
    graph.add_edge("package_case_node", END)
    return graph.compile()


CASE_TEST_MESSAGES = [
    "Please cancel order ACC-7001 before it ships. I placed it by mistake.",
    "My replacement request for account ACC-7002 is for a broken blender that arrived damaged.",
    "Can you update the address for order ACC-7003 before dispatch?",
    "Shipment ACC-7004 is 16 days late and still not delivered.",
    "Laptop ACC-7005 failed after one week and should be covered by warranty.",
    "Need help with account ACC-7006, something is wrong but I am not sure what action is needed.",
]
