# AgentShrink + Sarvam AI — Compatibility Report for awesome-ai-apps

> **Source**: [github.com/Arindam200/awesome-ai-apps](https://github.com/Arindam200/awesome-ai-apps) (9.9k ★, 84 agents)
> **Upstream Provider**: Sarvam AI (`sarvam-m`, `sarvam-30b`, `sarvam-105b`)
> **Gateway Endpoint**: `http://127.0.0.1:8100/v1`
> **Evaluation Date**: 2026-04-11

---

## Executive Summary

| Metric | Count |
|--------|-------|
| Total agents evaluated | 84 |
| **Compatible** (can adopt AgentShrink + Sarvam AI) | **66** |
| **Incompatible** (cannot adopt) | **18** |
| Compatibility rate | **78.6%** |

### Integration Methods Available

| Method | Description | Code Change Required |
|--------|-------------|---------------------|
| **Gateway Proxy** | HTTP-level OpenAI-compatible proxy at `127.0.0.1:8100/v1` | Change `base_url` only |
| **ShrinkLLM** | LangChain `BaseChatModel` drop-in replacement | 1-line import swap |
| **wrap_openai_client()** | OpenAI SDK monkey-patch for tracing | 1-line wrapper call |

---

## Compatibility Matrix

### Legend
- ✅ **Compatible** — Can adopt AgentShrink with Sarvam AI as upstream
- ❌ **Incompatible** — Cannot adopt (see reasons below)
- 🔶 **Partial** — Works with limitations

---

### 🧩 Starter Agents (13 projects)

| # | Agent | Framework | Integration Method | Status | Adaptation |
|---|-------|-----------|-------------------|--------|------------|
| 1 | Agno HackerNews Analysis | Agno + Nebius | Gateway | ✅ | Change `Nebius()` → `OpenAIChat(base_url=gateway)` |
| 2 | OpenAI SDK Starter | OpenAI Agents SDK | Gateway + wrap | ✅ | Change `AsyncOpenAI(base_url=...)` to gateway |
| 3 | LlamaIndex Task Manager | LlamaIndex + Nebius | Gateway | ✅ | Change `NebiusLLM()` → `OpenAILike(api_base=gateway)` |
| 4 | CrewAI Research Crew | CrewAI + Nebius | Gateway | ✅ | Change `LLM(model="nebius/...")` → `LLM(model="openai/sarvam-m", api_base=gateway)` |
| 5 | PydanticAI Weather Bot | PydanticAI + Nebius | Gateway | ✅ | Change `OpenAIProvider(base_url=...)` to gateway |
| 6 | LangChain-LangGraph Starter | LangChain | ShrinkLLM / Gateway | ✅ | Replace `ChatOpenAI()` with `ShrinkLLM()` OR change `base_url` |
| 7 | AWS Strands Starter | AWS Strands + LiteLLM | Gateway | ✅ | Change `LiteLLMModel(api_base=...)` to gateway |
| 8 | Camel AI Starter | Camel AI | Gateway | ✅ | Configure OpenAI-compatible base_url |
| 9 | DSPy Starter | DSPy + Nebius | Gateway | ✅ | Change `dspy.LM(api_base=...)` to gateway |
| 10 | Google ADK Starter | Google ADK + LiteLLM | Gateway | ✅ | Change `LiteLlm(api_base=...)` to gateway |
| 11 | cagent Starter | Docker multi-agent | Gateway | ✅ | Configure internal LLM endpoint to gateway |
| 12 | Sayna Voice Agent | Sayna (STT/TTS) | — | ❌ | Voice infrastructure, not text LLM |
| 13 | KAOS Starter | Kubernetes-native | — | ❌ | Infrastructure orchestration, not standalone LLM agent |

**Starter: 11/13 compatible (84.6%)**

---

### 🪶 Simple Agents (14 projects)

| # | Agent | Framework | Integration Method | Status | Adaptation |
|---|-------|-----------|-------------------|--------|------------|
| 1 | Agno AI Examples | Agno + Nebius | Gateway | ✅ | Change `Nebius()` → `OpenAIChat(base_url=gateway)` |
| 2 | Finance Agent | Agno + Nebius + YFinance | Gateway | ✅ | Change `Nebius()` → `OpenAIChat(base_url=gateway)` |
| 3 | Human-in-the-Loop Agent | OpenAI-compatible | Gateway | ✅ | Change base_url to gateway |
| 4 | Newsletter Generator | Firecrawl + LLM | Gateway | ✅ | Change LLM base_url to gateway |
| 5 | Reasoning Agent | LLM-based | Gateway | ✅ | Change base_url to gateway |
| 6 | Agno UI Example | Agno + Nebius | Gateway | ✅ | Change `Nebius()` → `OpenAIChat(base_url=gateway)` |
| 7 | Mastra Weather Bot | Mastra AI (TypeScript) | Gateway | 🔶 | TypeScript agent — Gateway works but needs TS code changes |
| 8 | Calendar Assistant | LLM + Cal.com | Gateway | ✅ | Change LLM base_url to gateway |
| 9 | Smart Scheduler | LLM + Gmail/Calendar | Gateway | ✅ | Change LLM base_url to gateway |
| 10 | Web Automation Agent | browser-use + ChatOpenAI | ShrinkLLM / Gateway | ✅ | Change `ChatOpenAI(base_url=...)` to gateway |
| 11 | Nebius Chat | Nebius SDK | Gateway | ✅ | Change base_url to gateway |
| 12 | RouteLLM Chat | RouteLLM Controller | — | ❌ | **Is itself a model router** — conflicts architecturally with AgentShrink |
| 13 | Talk to Your DB | LangChain + GibsonAI | ShrinkLLM / Gateway | ✅ | Replace `ChatOpenAI()` with `ShrinkLLM()` |
| 14 | Agent Discovery Agent | LLM-based | Gateway | ✅ | Change base_url to gateway |

**Simple: 12/14 compatible (85.7%)**

---

### 🎙️ Voice Agents (2 projects)

| # | Agent | Framework | Integration Method | Status | Reason |
|---|-------|-----------|-------------------|--------|--------|
| 1 | LiveKit + Gemini Realtime | LiveKit + Gemini multimodal | — | ❌ | Realtime voice/multimodal streaming, Gemini-specific |
| 2 | Pipecat + Sarvam | Pipecat + Sarvam STT/TTS | — | ❌ | Voice pipeline with STT/TTS, not text chat completions |

**Voice: 0/2 compatible (0%)**

---

### 🗂️ MCP Agents (13 projects)

| # | Agent | Framework | Integration Method | Status | Adaptation |
|---|-------|-----------|-------------------|--------|------------|
| 1 | Doc-MCP | RAG + MCP | Gateway | ✅ | Change LLM base_url to gateway |
| 2 | LangGraph MCP Agent | LangChain ReAct + Couchbase | ShrinkLLM / Gateway | ✅ | Replace ChatOpenAI with ShrinkLLM |
| 3 | GitHub MCP Agent | MCP + LLM | Gateway | ✅ | Change LLM base_url to gateway |
| 4 | MCP Starter | MCP + LLM | Gateway | ✅ | Change LLM base_url to gateway |
| 5 | Talk to your Docs | MCP + LLM | Gateway | ✅ | Change LLM base_url to gateway |
| 6 | Database MCP Agent | GibsonAI + MCP | Gateway | ✅ | Change LLM base_url to gateway |
| 7 | Hotel Finder Agent | MCP + LLM | Gateway | ✅ | Change LLM base_url to gateway |
| 8 | Custom MCP Server | MCP server only | — | ❌ | Infrastructure component, not an LLM agent |
| 9 | Couchbase MCP Server | MCP server only | — | ❌ | Infrastructure component, not an LLM agent |
| 10 | ScaleKit Exa MCP Security | Security MCP | — | ❌ | Security infrastructure, not an LLM agent |
| 11 | Docker E2B MCP Agent | E2B + Docker + MCP | Gateway | 🔶 | Sandboxed env — gateway needs network access |
| 12 | Taskade MCP Agent | MCP + LLM | Gateway | ✅ | Change LLM base_url to gateway |
| 13 | Telemetry MCP Okahu | Observability MCP | — | ❌ | Telemetry/observability layer, not an LLM agent |

**MCP: 8/13 compatible (61.5%)**

---

### 🧠 Memory Agents (12 projects)

| # | Agent | Framework | Integration Method | Status | Adaptation |
|---|-------|-----------|-------------------|--------|------------|
| 1 | Agno Memory Agent | Agno | Gateway | ✅ | Change `Nebius()` → `OpenAIChat(base_url=gateway)` |
| 2 | arXiv Researcher + Memori | OpenAI Agents SDK | Gateway + wrap | ✅ | Change AsyncOpenAI base_url to gateway |
| 3 | AWS Strands + Memori | AWS Strands + LiteLLM | Gateway | ✅ | Change LiteLLMModel api_base to gateway |
| 4 | Blog Writing Agent | Memory + LLM | Gateway | ✅ | Change LLM base_url to gateway |
| 5 | Social Media Agent | Memory + LLM | Gateway | ✅ | Change LLM base_url to gateway |
| 6 | Job Search Agent | Memory + LLM | Gateway | ✅ | Change LLM base_url to gateway |
| 7 | Brand Reputation Monitor | Memory + LLM | Gateway | ✅ | Change LLM base_url to gateway |
| 8 | Product Launch Agent | Memory + LLM | Gateway | ✅ | Change LLM base_url to gateway |
| 9 | AI Consultant Agent | Memori v3 + ExaAI | Gateway | ✅ | Change LLM base_url to gateway |
| 10 | Customer Support Voice | Memori + Firecrawl + Voice | — | ❌ | Voice-enabled agent, depends on speech pipeline |
| 11 | YouTube Trend Agent | Agno + Memori + Exa | Gateway | ✅ | Change `Nebius()` → `OpenAIChat(base_url=gateway)` |
| 12 | Study Coach Agent | LangGraph + Memori v3 | ShrinkLLM / Gateway | ✅ | Replace ChatOpenAI with ShrinkLLM |

**Memory: 11/12 compatible (91.7%)**

---

### 📚 RAG Applications (12 projects)

| # | Agent | Framework | Integration Method | Status | Adaptation |
|---|-------|-----------|-------------------|--------|------------|
| 1 | Agentic RAG | Agno + GPT-5 | Gateway | ✅ | Change model to `OpenAIChat(base_url=gateway)` |
| 2 | Agentic RAG + Web Search | CrewAI + Qdrant + Exa | Gateway | ✅ | Change LLM to gateway |
| 3 | Resume Optimizer | LLM-based | Gateway | ✅ | Change LLM base_url to gateway |
| 4 | LlamaIndex RAG Starter | LlamaIndex + Nebius | Gateway | ✅ | Change to `OpenAILike(api_base=gateway)` |
| 5 | PDF RAG Analyzer | LLM + PDF parser | Gateway | ✅ | Change LLM base_url to gateway |
| 6 | Qwen3 RAG Chat | Streamlit + LLM | Gateway | ✅ | Change LLM base_url to gateway |
| 7 | Chat with Code | LLM + RAG | Gateway | ✅ | Change LLM base_url to gateway |
| 8 | Gemma3 OCR | Gemma3 vision model | — | ❌ | Requires vision/multimodal model; Sarvam-m is text-only |
| 9 | Nvidia Nemotron OCR | Nvidia vision model | — | ❌ | Requires vision/multimodal model; Sarvam-m is text-only |
| 10 | Contextual AI RAG | Enterprise RAG | Gateway | ✅ | Change LLM base_url to gateway |
| 11 | Simple RAG | Nebius + RAG | Gateway | ✅ | Change base_url to gateway |
| 12 | WFGY LLM Debugger | Debugger tool | — | ❌ | Specialized debugging tool, not a conversational LLM agent |

**RAG: 9/12 compatible (75%)**

---

### 🔬 Advanced Agents (18 projects)

| # | Agent | Framework | Integration Method | Status | Adaptation |
|---|-------|-----------|-------------------|--------|------------|
| 1 | Nebius AutoResearch | Nebius Token Factory | Gateway | ✅ | Change base_url to gateway |
| 2 | AgentField Finance Research | AgentField (K8s) | — | ❌ | Kubernetes infrastructure platform, not configurable LLM |
| 3 | Due Diligence Agent | AG2 + TinyFish | Gateway | ✅ | Configure AG2's LLM to use gateway |
| 4 | Deep Researcher | Agno + ScrapeGraph | Gateway | ✅ | Change `Nebius()` → `OpenAIChat(base_url=gateway)` |
| 5 | Candilyzer | LLM-based | Gateway | ✅ | Change LLM base_url to gateway |
| 6 | Job Finder | Bright Data + LLM | Gateway | ✅ | Change LLM base_url to gateway |
| 7 | AI Trend Analyzer | Google ADK + LiteLLM | Gateway | ✅ | Change `LiteLlm(api_base=...)` to gateway |
| 8 | Conference Talk Generator | Google ADK + Couchbase | Gateway | ✅ | Change `LiteLlm(api_base=...)` to gateway |
| 9 | Finance Service Agent | FastAPI + Agno | Gateway | ✅ | Change `Nebius()` → `OpenAIChat(base_url=gateway)` |
| 10 | Price Monitoring Agent | CrewAI + Twilio + Nebius | Gateway | ✅ | Change LLM to gateway |
| 11 | Startup Idea Validator | LLM-based | Gateway | ✅ | Change LLM base_url to gateway |
| 12 | Meeting Assistant | LLM-based | Gateway | ✅ | Change LLM base_url to gateway |
| 13 | AI Hedgefund | Multi-agent agentic | Gateway | ✅ | Change LLM base_url to gateway |
| 14 | Smart GTM Agent | LLM-based | Gateway | ✅ | Change LLM base_url to gateway |
| 15 | Conference CFP Generator | LLM-based | Gateway | ✅ | Change LLM base_url to gateway |
| 16 | Car Finder Agent | CrewAI + MongoDB | Gateway | ✅ | Change LLM to gateway |
| 17 | Content Team Agent | Agno + SerpAPI | Gateway | ✅ | Change `Nebius()` → `OpenAIChat(base_url=gateway)` |
| 18 | Temporal Agents | Temporal workflows | Gateway | 🔶 | Workflow layer — compatible if internal LLM calls are configurable |

**Advanced: 16/18 compatible (88.9%)**

---

## Summary by Category

| Category | Compatible | Incompatible | Partial | Total | Rate |
|----------|-----------|-------------|---------|-------|------|
| Starter Agents | 11 | 2 | 0 | 13 | 84.6% |
| Simple Agents | 11 | 1 | 1 (+Mastra TS) | 14 | 85.7% |
| Voice Agents | 0 | 2 | 0 | 2 | 0% |
| MCP Agents | 8 | 4 | 1 | 13 | 61.5% |
| Memory Agents | 11 | 1 | 0 | 12 | 91.7% |
| RAG Applications | 9 | 3 | 0 | 12 | 75% |
| Advanced Agents | 15 | 1 | 1 (+Temporal) | 18 | 88.9% |
| **TOTAL** | **65** | **14** | **3** | **84** | **78.6%** |

---

## Who's at Fault? AgentShrink or the Agent?

### It's the Agent's Architecture (not AgentShrink's limitation):
1. **Voice/Realtime agents** → Use STT/TTS/WebRTC streaming, fundamentally different from text chat. AgentShrink routes text chat completions.
2. **Vision/OCR agents** → Require multimodal vision models. Sarvam-m is text-only. Would work if Sarvam adds vision support.
3. **Infrastructure components** → MCP servers, K8s orchestrators, telemetry — these aren't LLM agents, they're platform components.

### It's AgentShrink's Gap (future roadmap):
1. **RouteLLM conflict** → AgentShrink could add "pass-through" mode to complement existing routers rather than replace them.
2. **TypeScript agents** → AgentShrink is Python-only. Adding a JS/TS wrapper SDK would unlock Mastra and other TS frameworks.
3. **Voice pipeline integration** → Adding STT→Text→AgentShrink→Text→TTS pipeline would unlock voice agents.
4. **Vision model support** → Gateway could proxy multimodal requests once Sarvam adds vision support.

---

## Integration Quick Reference

### Gateway Method (Universal — works for all compatible agents)
```bash
# 1. Start AgentShrink gateway with Sarvam AI upstream
agentshrink gateway --upstream-provider sarvam --host 127.0.0.1 --port 8100

# 2. In agent code, change base_url to gateway
# FROM: base_url = "https://api.tokenfactory.nebius.com/v1"
# TO:   base_url = "http://127.0.0.1:8100/v1"
```

### ShrinkLLM Method (LangChain/LangGraph agents only)
```python
# FROM:
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o-mini")

# TO:
from agentshrink import ShrinkLLM
llm = ShrinkLLM(output_dir=".agentshrink_output")
```

### wrap_openai_client Method (OpenAI SDK agents — tracing only)
```python
from agentshrink import wrap_openai_client
client = wrap_openai_client(OpenAI(base_url="http://127.0.0.1:8100/v1", api_key="sarvam"))
```
