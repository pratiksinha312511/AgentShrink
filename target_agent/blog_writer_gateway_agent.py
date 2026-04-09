from __future__ import annotations

import os
import uuid
import json
from pathlib import Path
from typing import Dict

from openai import OpenAI

from agentshrink.app_setup import load_product_config


def _gateway_defaults() -> tuple[str, str, str]:
    config = load_product_config()
    gateway = config.get("gateway") or {}
    defaults = config.get("defaults") or {}

    base_url = os.getenv(
        "AGENTSHRINK_GATEWAY_BASE_URL",
        f"http://{gateway.get('host', '127.0.0.1')}:{gateway.get('port', 8100)}/v1",
    )
    api_key = os.getenv(
        "AGENTSHRINK_GATEWAY_API_KEY",
        defaults.get("gateway_api_key") or "agentshrink-local",
    )
    model = os.getenv(
        "AGENTSHRINK_GATEWAY_MODEL",
        defaults.get("gateway_model") or "mock-model",
    )
    return base_url, api_key, model


def _build_blog_prompt(topic: str, writing_style_context: str = "") -> str:
    """
    Minimal adaptation of:
      memory_agents/blog_writing_agent/agents.py -> generate_blog_with_style()

    AgentShrink guide changes only:
    - swap OpenAI-compatible base_url to AgentShrink gateway
    - swap api_key to AgentShrink project token / gateway key
    - keep standard OpenAI client usage
    """
    if writing_style_context:
        return f"Write a blog post about {topic}. Use this writing style: {writing_style_context}"
    return (
        f"Write a professional and engaging blog post about {topic}. "
        "Make it informative, well-structured, and easy to read."
    )


def _build_style_analysis_prompt(text: str) -> str:
    excerpt = text[:3000]
    return f"""
Analyze the following text and extract the author's writing style characteristics.
Focus on:
1. Tone
2. Writing structure
3. Vocabulary level and complexity
4. Sentence structure patterns
5. Use of examples, analogies, or storytelling
6. Overall voice and personality

Text to analyze:
{excerpt}

Provide your analysis in JSON format with these keys:
- tone
- structure
- vocabulary
- sentence_patterns
- examples_style
- voice
- writing_habits
"""


def create_blog_writer_gateway_client(*, run_id: str | None = None) -> tuple[OpenAI, str, str]:
    base_url, api_key, model = _gateway_defaults()
    resolved_run_id = run_id or f"blog-writer-{uuid.uuid4().hex[:8]}"
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        default_headers={
            "x-agentshrink-node": "blog_writer_gateway_demo",
            "x-agentshrink-run-id": resolved_run_id,
        },
    )
    return client, model, resolved_run_id


def generate_blog_post_with_client(
    client: OpenAI,
    model: str,
    topic: str,
    *,
    writing_style_context: str = "",
) -> str:
    prompt = _build_blog_prompt(topic, writing_style_context=writing_style_context)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=1200,
    )
    return (response.choices[0].message.content or "").strip()


def analyze_writing_style_with_client(
    client: OpenAI,
    model: str,
    text: str,
) -> dict:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are an expert writing analyst. Analyze the writing style and return JSON when possible.",
            },
            {
                "role": "user",
                "content": _build_style_analysis_prompt(text),
            },
        ],
        temperature=0.3,
        max_tokens=1200,
    )
    content = (response.choices[0].message.content or "").strip()
    try:
        return json.loads(content)
    except Exception:
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            if end > start:
                return json.loads(content[start:end].strip())
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(content[start:end + 1])
        return {
            "tone": "Unable to parse structured style analysis",
            "structure": "No structured JSON could be extracted from the provider response.",
            "vocabulary": "Unknown",
            "sentence_patterns": "Unknown",
            "examples_style": "Unknown",
            "voice": "Unknown",
            "writing_habits": [content[:300] or "No response content returned."],
        }


def generate_blog_post_via_gateway(
    topic: str,
    *,
    writing_style_context: str = "",
    run_id: str | None = None,
) -> tuple[str, str]:
    client, model, resolved_run_id = create_blog_writer_gateway_client(run_id=run_id)
    content = generate_blog_post_with_client(
        client,
        model,
        topic,
        writing_style_context=writing_style_context,
    )
    return content, resolved_run_id


def analyze_writing_style_via_gateway(
    text: str,
    *,
    run_id: str | None = None,
) -> tuple[dict, str]:
    client, model, resolved_run_id = create_blog_writer_gateway_client(run_id=run_id)
    analysis = analyze_writing_style_with_client(client, model, text)
    return analysis, resolved_run_id


def load_blog_topics(path: str | Path) -> list[str]:
    file_path = Path(path)
    return [
        line.strip()
        for line in file_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_categorized_prompts(path: str | Path) -> Dict[str, list[str]]:
    file_path = Path(path)
    categories: Dict[str, list[str]] = {}
    current_key = ""
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("===") and "Category" in line:
            heading = line.strip("= ").strip()
            current_key = (
                heading.lower()
                .replace("—", "-")
                .replace(" ", "_")
                .replace("-", "_")
            )
            categories[current_key] = []
            continue
        if current_key and line[0].isdigit() and ". " in line:
            categories[current_key].append(line.split(". ", 1)[1].strip())
    return categories
