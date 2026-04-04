"""
AgentShrink-friendly adaptation of the original startup_idea_validator_agent.

This version keeps the same 4-step logic, but makes each node's prompt shape
more stable so clustering can separate the workflow more clearly.
"""

from __future__ import annotations

import json
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from target_agent.agent import get_llm
from target_agent import startup_validator_prompts as prompts


class StartupValidationState(TypedDict):
    idea: str
    clarified_idea: dict
    market_research: dict
    competitor_analysis: dict
    validation_report: dict
    final_summary: str


def _compact_text(value) -> str:
    if isinstance(value, list):
        text = "; ".join(str(item).strip() for item in value if str(item).strip())
    else:
        text = str(value or "").strip()
    return " ".join(text.split())[:240]


def _clarified_summary(clarified: dict) -> str:
    return (
        f"Originality: {_compact_text(clarified.get('originality', ''))} | "
        f"Mission: {_compact_text(clarified.get('mission', ''))} | "
        f"Objectives: {_compact_text(clarified.get('objectives', []))}"
    )


def _market_summary(market: dict) -> str:
    return (
        f"TAM: {_compact_text(market.get('total_addressable_market', ''))} | "
        f"SAM: {_compact_text(market.get('serviceable_available_market', ''))} | "
        f"SOM: {_compact_text(market.get('serviceable_obtainable_market', ''))} | "
        f"Segments: {_compact_text(market.get('target_customer_segments', []))}"
    )


def _competitor_summary(competitor: dict) -> str:
    return (
        f"Competitors: {_compact_text(competitor.get('competitors', []))} | "
        f"SWOT: {_compact_text(competitor.get('swot_analysis', ''))} | "
        f"Positioning: {_compact_text(competitor.get('positioning', ''))}"
    )


def _safe_json_parse(content: str, fallback: dict) -> dict:
    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json\n", "", 1).strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else fallback
    except Exception:
        return fallback


def clarify_idea_node(state: StartupValidationState, callbacks=None) -> StartupValidationState:
    llm = get_llm(callbacks)
    messages = [
        SystemMessage(content=prompts.IDEA_PROMPT.format(idea=state["idea"])),
        HumanMessage(content=f"Startup idea: {state['idea']}"),
    ]
    response = llm.invoke(messages)
    clarified = _safe_json_parse(
        response.content,
        {
            "originality": "Could not parse originality cleanly.",
            "mission": "Could not parse mission cleanly.",
            "objectives": ["Could not parse objectives cleanly."],
        },
    )
    return {**state, "clarified_idea": clarified}


def market_research_node(state: StartupValidationState, callbacks=None) -> StartupValidationState:
    llm = get_llm(callbacks)
    clarified = state["clarified_idea"]
    messages = [
        SystemMessage(
            content=prompts.MARKET_RESEARCH_PROMPT.format(
                idea=state["idea"],
                clarified_summary=_clarified_summary(clarified),
            )
        ),
        HumanMessage(content=f"Research the market for this startup idea: {state['idea']}"),
    ]
    response = llm.invoke(messages)
    market_research = _safe_json_parse(
        response.content,
        {
            "total_addressable_market": "Not available",
            "serviceable_available_market": "Not available",
            "serviceable_obtainable_market": "Not available",
            "target_customer_segments": ["Not available"],
        },
    )
    return {**state, "market_research": market_research}


def competitor_analysis_node(state: StartupValidationState, callbacks=None) -> StartupValidationState:
    llm = get_llm(callbacks)
    market = state["market_research"]
    messages = [
        SystemMessage(
            content=prompts.COMPETITOR_ANALYSIS_PROMPT.format(
                idea=state["idea"],
                market_summary=_market_summary(market),
            )
        ),
        HumanMessage(content=f"Analyze the competitors for this startup idea: {state['idea']}"),
    ]
    response = llm.invoke(messages)
    competitor_analysis = _safe_json_parse(
        response.content,
        {
            "competitors": ["Not available"],
            "swot_analysis": "Not available",
            "positioning": "Not available",
        },
    )
    return {**state, "competitor_analysis": competitor_analysis}


def report_generation_node(state: StartupValidationState, callbacks=None) -> StartupValidationState:
    llm = get_llm(callbacks)
    clarified = state["clarified_idea"]
    market = state["market_research"]
    competitor = state["competitor_analysis"]
    messages = [
        SystemMessage(
            content=prompts.REPORT_PROMPT.format(
                idea=state["idea"],
                idea_summary=_clarified_summary(clarified),
                market_summary=_market_summary(market),
                competitor_summary=_competitor_summary(competitor),
            )
        ),
        HumanMessage(content=f"Generate a validation report for this startup idea: {state['idea']}"),
    ]
    response = llm.invoke(messages)
    report = _safe_json_parse(
        response.content,
        {
            "executive_summary": "Report unavailable",
            "idea_assessment": "Report unavailable",
            "market_opportunity": "Report unavailable",
            "competition": "Report unavailable",
            "risks": ["Report unavailable"],
            "go_to_market": ["Report unavailable"],
            "verdict": "refine",
        },
    )
    final_summary = (
        f"Verdict: {report.get('verdict', 'unknown')} | "
        f"Summary: {_compact_text(report.get('executive_summary', ''))}"
    )
    return {**state, "validation_report": report, "final_summary": final_summary}


def build_startup_validator_agent(callbacks=None):
    graph = StateGraph(StartupValidationState)

    def clarify(state: StartupValidationState):
        return clarify_idea_node(state, callbacks)

    def market(state: StartupValidationState):
        return market_research_node(state, callbacks)

    def competitor(state: StartupValidationState):
        return competitor_analysis_node(state, callbacks)

    def report(state: StartupValidationState):
        return report_generation_node(state, callbacks)

    graph.add_node("clarify_idea_node", clarify)
    graph.add_node("market_research_node", market)
    graph.add_node("competitor_analysis_node", competitor)
    graph.add_node("report_generation_node", report)

    graph.add_edge(START, "clarify_idea_node")
    graph.add_edge("clarify_idea_node", "market_research_node")
    graph.add_edge("market_research_node", "competitor_analysis_node")
    graph.add_edge("competitor_analysis_node", "report_generation_node")
    graph.add_edge("report_generation_node", END)

    return graph.compile()


TEST_IDEAS = [
    "An AI agent that reviews pull requests and explains bugs before merge.",
    "A startup that generates investor-ready pitch decks from product notes and traction metrics.",
    "A voice AI coach for inside sales teams that scores calls and suggests follow-ups.",
    "A restaurant analytics copilot that forecasts waste and inventory needs from POS data.",
    "A recruiting assistant that summarizes candidates and drafts scorecards from interviews.",
]
