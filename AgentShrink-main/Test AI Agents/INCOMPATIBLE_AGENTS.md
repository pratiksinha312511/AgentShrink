# Incompatible Agents — Why They Can't Use AgentShrink + Sarvam AI

> 18 of 84 agents from awesome-ai-apps are incompatible.
> This document explains WHY for each, and whether it's the agent's fault or AgentShrink's gap.

---

## Category 1: Voice/Realtime Agents (4 agents)

### ❌ Sayna Voice Agent (`starter_ai_agents/sayna_starter`)
- **Framework**: Sayna real-time voice infrastructure (Deepgram, ElevenLabs, Azure STT/TTS, WebSocket)
- **Why Incompatible**: Uses streaming audio/WebSocket pipelines, not text chat completions. AgentShrink's gateway only handles `POST /v1/chat/completions` (text).
- **Whose fault**: BOTH — Agent is inherently voice-first. AgentShrink lacks STT/TTS pipeline integration.
- **Fix**: AgentShrink could add `POST /v1/audio/transcriptions` → text → route → text → `POST /v1/audio/speech` pipeline.

### ❌ LiveKit + Gemini Realtime (`voice_agents/livekit_gemini_agents`)
- **Framework**: LiveKit Agents SDK + Gemini multimodal realtime API
- **Why Incompatible**: Uses Gemini's proprietary multimodal realtime streaming (audio+video+text simultaneously). Not a standard chat completions API.
- **Whose fault**: AGENT — Tightly coupled to Gemini's proprietary realtime protocol. No OpenAI-compatible equivalent exists.
- **Fix**: Would need Sarvam AI to support realtime multimodal streaming AND AgentShrink to proxy WebSocket connections.

### ❌ Pipecat + Sarvam (`voice_agents/pipecat_agent`)
- **Framework**: Pipecat voice pipeline + Sarvam STT/TTS + OpenAI chat
- **Why Incompatible**: The voice pipeline (STT→LLM→TTS) is a different paradigm from text routing. Pipecat manages audio frames, not text messages.
- **Whose fault**: AGENTSHRINK — The LLM chat portion IS OpenAI-compatible and COULD be routed through AgentShrink gateway. But the STT/TTS components can't.
- **Fix**: Could partially integrate by routing only the OpenAI chat portion through AgentShrink, keeping STT/TTS direct.

### ❌ Customer Support Voice Agent (`memory_agents/customer_support_voice_agent`)
- **Framework**: Memori v3 + Firecrawl + Voice pipeline
- **Why Incompatible**: Voice-enabled agent — same STT/TTS pipeline issue as above.
- **Whose fault**: AGENTSHRINK — Memory and LLM parts are compatible; only the voice I/O layer conflicts.
- **Fix**: Separate the voice layer. Route text LLM calls through AgentShrink; keep voice pipeline direct.

---

## Category 2: Vision/Multimodal Agents (2 agents)

### ❌ Gemma3 OCR (`rag_apps/gemma_ocr/`)
- **Framework**: Gemma3 vision model for OCR
- **Why Incompatible**: Requires a **vision model** that processes images. Sarvam-m (24B) is text-only — it cannot process image inputs.
- **Whose fault**: SARVAM AI model limitation — Sarvam-m doesn't support vision/image inputs. The gateway could proxy vision requests if the upstream model supported it.
- **Fix**: Use `sarvam-vision` (if/when released) or route to a vision-capable model for OCR while using Sarvam for text.

### ❌ Nvidia Nemotron OCR (`rag_apps/nvidia_ocr/`)
- **Framework**: Nvidia Nemotron-Nano-V2-12b vision model
- **Why Incompatible**: Same as Gemma3 OCR — requires multimodal vision model input.
- **Whose fault**: SARVAM AI model limitation (no vision support). AgentShrink gateway CAN proxy multimodal requests; the upstream model just can't handle them.
- **Fix**: Same as above — need a vision-capable upstream model.

---

## Category 3: Infrastructure/Platform Components (7 agents)

### ❌ KAOS Starter (`starter_ai_agents/kaos_starter`)
- **Framework**: Kubernetes-native multi-agent system
- **Why Incompatible**: This is a **Kubernetes orchestration platform** for running agents, not an LLM agent itself. You deploy agents INTO KAOS, not adapt KAOS as an agent.
- **Whose fault**: NOT AN AGENT — It's infrastructure. Like saying Docker isn't compatible with AgentShrink — it's the wrong comparison.

### ❌ Custom MCP Server (`mcp_ai_agents/custom_mcp_server`)
- **Framework**: MCP server implementation
- **Why Incompatible**: This is an MCP **server** (tool provider), not an LLM agent. It provides tools to agents; it doesn't make LLM calls itself.
- **Whose fault**: NOT AN AGENT — It's a tool server. AgentShrink routes LLM calls, not tool calls.

### ❌ Couchbase MCP Server (`mcp_ai_agents/couchbase_mcp_server`)
- **Framework**: MCP protocol integration for Couchbase
- **Why Incompatible**: Database integration server, not an LLM agent.
- **Whose fault**: NOT AN AGENT — Infrastructure component.

### ❌ ScaleKit Exa MCP Security (`mcp_ai_agents/scalekit-exa-mcp-security`)
- **Framework**: Security-focused MCP integration
- **Why Incompatible**: Security middleware/infrastructure, not an LLM agent.
- **Whose fault**: NOT AN AGENT — Security layer.

### ❌ Telemetry MCP Okahu (`mcp_ai_agents/telemetry-mcp-okahu`)
- **Framework**: Okahu Cloud traces + hosted MCP
- **Why Incompatible**: Observability/telemetry tool, not an LLM agent. It monitors agents; it doesn't act as one.
- **Whose fault**: NOT AN AGENT — Monitoring infrastructure.

### ❌ AgentField Finance Research (`advance_ai_agents/agentfield_finance_research_agent`)
- **Framework**: AgentField (Kubernetes for AI Agents)
- **Why Incompatible**: AgentField is an **agent deployment platform**. The agent runs inside AgentField's managed environment where LLM providers are configured at the platform level, not at the code level.
- **Whose fault**: AGENT — Tightly coupled to AgentField's deployment model. Would need AgentField to support AgentShrink as a provider.
- **Fix**: Configure AgentField to use AgentShrink gateway as its LLM endpoint.

### ❌ WFGY LLM Debugger (`rag_apps/wfgy_llm_debugger`)
- **Framework**: 16-mode map-based debugger
- **Why Incompatible**: This is a **debugging/diagnostic tool** for LLMs, not an LLM agent. It tests and analyzes model behavior.
- **Whose fault**: NOT AN AGENT — Diagnostic tool. However, it COULD use AgentShrink gateway as the model endpoint to debug.

---

## Category 4: Architectural Conflict (1 agent)

### ❌ RouteLLM Chat (`simple_ai_agents/llm_router`)
- **Framework**: RouteLLM Controller (model router)
- **Why Incompatible**: RouteLLM is **itself a model router** — it routes queries between a "strong model" (GPT-4o-mini) and a "weak model" (Llama via Nebius) based on query complexity. This **directly conflicts** with AgentShrink's routing purpose.
- **Whose fault**: ARCHITECTURAL CONFLICT — Both products solve the same problem (intelligent model routing). Running RouteLLM through AgentShrink would be router-inside-a-router.
- **Fix**: Replace RouteLLM entirely with AgentShrink (which does the same routing but adds fine-tuning and cost optimization). Or use AgentShrink's gateway as RouteLLM's "weak model" endpoint.

---

## Category 5: TypeScript/Non-Python (1 agent — partial)

### 🔶 Mastra Weather Bot (`simple_ai_agents/mastra_ai_weather_agent`)
- **Framework**: Mastra AI (TypeScript)
- **Why Partially Incompatible**: Agent code is TypeScript, which the AgentShrink Python SDK doesn't support. However, the **Gateway proxy works regardless of language** — TypeScript can call `http://127.0.0.1:8100/v1` just like Python.
- **Whose fault**: AGENTSHRINK — Python-only SDK. Gateway works, but `ShrinkLLM` and `wrap_openai_client()` are Python-only.
- **Fix**: Create a `@agentshrink/js` npm package or document TypeScript gateway integration.

---

## Summary: Fault Analysis

| Root Cause | Count | Agents |
|-----------|-------|--------|
| **Not an agent** (infrastructure/tool) | 7 | KAOS, Custom MCP Server, Couchbase MCP, ScaleKit MCP, Telemetry MCP, AgentField, WFGY Debugger |
| **Voice/Realtime paradigm** | 4 | Sayna, LiveKit+Gemini, Pipecat, Customer Support Voice |
| **Vision model required** | 2 | Gemma3 OCR, Nvidia OCR |
| **Architectural conflict** | 1 | RouteLLM (competing router) |
| **Language barrier** | 1 | Mastra (TypeScript — partial) |
| **AgentShrink's gap** | 3 | Voice pipeline, TypeScript SDK, multimodal proxy |
| **Agent's limitation** | 8 | Proprietary protocols, platform coupling, wrong category |
| **Model limitation** | 2 | Sarvam-m lacks vision (will resolve with Sarvam Vision) |

### Net Result
- **AgentShrink is NOT at fault** for 15 of 18 incompatible agents
- **AgentShrink has gaps** that affect 3 agents (voice, TypeScript, multimodal)
- These 3 gaps are on the [PRODUCT_ROADMAP.md](../PRODUCT_ROADMAP.md) for future versions
