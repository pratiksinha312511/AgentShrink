# Sarvam AI Provider — Setup Guide

## Quick Start

### 1. Sarvam AI is now a built-in provider in AgentShrink

Added to `agentshrink/provider_runtime.py` as:
```json
{
  "id": "sarvam",
  "name": "Sarvam AI",
  "adapter": "openai_compatible",
  "base_url": "https://api.sarvam.ai/v1",
  "default_model": "sarvam-m",
  "api_key_env": "SARVAM_API_KEY"
}
```

### 2. API Key Configuration

Already set in `.env`:
```
SARVAM_API_KEY=sk_n1ml3hq3_KKAGsSqmsUiTRPOhbQruicRH
```

### 3. Available Sarvam AI Models

| Model | Parameters | Context | Status |
|-------|-----------|---------|--------|
| `sarvam-m` | 24B | — | Legacy (still accepted) |
| `sarvam-30b` | 30B (2.4B active MoE) | 64K tokens | Recommended |
| `sarvam-105b` | 105B | 128K tokens | Flagship |

### 4. Start Gateway with Sarvam AI

```bash
cd D:\CampusLearning\AgentShrink-main\AgentShrink-main

# Start gateway with Sarvam AI as upstream
python -m agentshrink.cli gateway --upstream-provider sarvam --host 127.0.0.1 --port 8100

# Or use the stack command
python -m agentshrink.cli stack up
```

### 5. Test the Connection

```bash
curl -X POST http://127.0.0.1:8100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer project-token" \
  -d '{
    "model": "sarvam-m",
    "messages": [{"role": "user", "content": "Hello from AgentShrink!"}]
  }'
```

### 6. Use in Any Agent

```python
# Point any OpenAI-compatible client to the gateway
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8100/v1",
    api_key="project-token"
)

response = client.chat.completions.create(
    model="sarvam-m",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```

---

## Sarvam AI Special Features (via gateway)

- **Indic Language Support**: Native support for Hindi, Tamil, Telugu, Bengali, Marathi, and more
- **Tool Calling**: Built-in function/tool calling support
- **Reasoning Mode**: Set `reasoning_effort` (low/medium/high) for complex tasks
- **Wiki Grounding**: Set `wiki_grounding=true` for fact-checked responses
- **Streaming**: Full SSE streaming support

## Authentication Methods

Sarvam AI accepts both:
1. `Authorization: Bearer <api_key>` (standard OpenAI format — used by gateway)
2. `api-subscription-key: <api_key>` (custom header)

The `openai_compatible` adapter uses method 1, which works perfectly.
