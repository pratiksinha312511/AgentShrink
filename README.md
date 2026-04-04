# AgentShrink 🔬

> **Automatically convert any LLM-powered agent to use cheaper, faster local SLMs.**
>
> Implements the LLM-to-SLM conversion algorithm from NVIDIA Research:
> [arXiv:2506.02153](https://arxiv.org/abs/2506.02153) — *"Small Language Models are the Future of Agentic AI"* (June 2025)

---

## The Problem

Every AI agent built today uses GPT-4o or Claude for **every** LLM call — including trivial tasks like classifying a complaint type or formatting JSON output. According to NVIDIA's research, **40–70% of those calls don't need a large model**. They're simple, repetitive tasks that a free local 2B model handles equally well.

AgentShrink finds those calls automatically and replaces them.

## The One-Word Change

```python
# BEFORE — standard agent
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o-mini")

# AFTER — AgentShrink active. Everything else unchanged.
from agentshrink import ShrinkLLM
llm = ShrinkLLM(output_dir=".agentshrink_output")
```

Your LangGraph nodes, tools, memory, callbacks — all unchanged. Zero rewriting.

## How It Works

AgentShrink implements the paper's 6-step **S1–S6 conversion algorithm**:

```
S1  Instrument  →  Add 1-line logger. Captures every LLM call to SQLite.
S2  Curate      →  Remove PII, deduplicate near-identical prompts.
S3  Cluster     →  HDBSCAN on sentence embeddings discovers task groups.
S4  Evaluate    →  Benchmark local SLMs on each cluster (LLM-as-judge scoring).
S5  Fine-tune   →  QLoRA on Colab T4 (free) for borderline clusters.
S6  Route       →  ShrinkLLM intercepts calls, routes by centroid similarity (~10ms).
```

## Benchmark Results

| Metric | Before AgentShrink | After AgentShrink |
|--------|--------------------|-------------------|
| API calls per run | 5 / 5 (100%) | ~2 / 5 |
| Local SLM routing | 0% | **~60–70%** |
| Cost per 10,000 runs | $1.35 | **$0.41** |
| Cost reduction | — | **~70%** |
| Quality preserved | — | **85–92%** |
| Avg latency (simple tasks) | 800ms | **28ms** |

*Run `python benchmark/run_benchmark.py` to reproduce on your agent.*

> Validates arXiv:2506.02153 Appendix B — 40–70% of agentic LLM calls are SLM-replaceable.

## Architecture

```
agentshrink/
├── logger.py           S1  — LangChain callback → SQLite
├── curator.py          S2  — PII masking + deduplication
├── clusterer.py        S3  — HDBSCAN + UMAP task clustering
├── evaluator.py        S4  — SLM benchmarking + LLM-as-judge
├── finetuner.py        S5  — QLoRA dataset export + Colab notebook
├── centroid_index.py   S6  — Fast centroid routing (~10ms)
└── shrink_llm.py       S6  — Drop-in LangChain BaseChatModel

dashboard/
├── backend/main.py         FastAPI — REST + WebSocket
└── frontend/src/app/       Next.js — 6 screens

target_agent/agent.py       Test subject (5-node LangGraph agent)
benchmark/run_benchmark.py  Before/after measurement
```

## Quick Start

### Product-style local onboarding

```bash
agentshrink init --project-name "My AgentShrink Project"
agentshrink doctor
agentshrink start guide
```

Then open three terminals:

```bash
agentshrink start gateway
agentshrink start backend
agentshrink start frontend
```

Point any OpenAI-compatible app at:

```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:8100/v1", api_key="agentshrink-local")
```

This uses free `mock` mode by default, so you can validate the full product flow without spending money.

See [docs/USER_QUICKSTART.md](docs/USER_QUICKSTART.md) and [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md).

### Research/developer quick start

```bash
# 1. Clone and install
git clone https://github.com/yourusername/agentshrink
cd agentshrink
pip install -r requirements.txt
pip install -e .
cp .env.example .env         # Add OPENAI_API_KEY

# 2. Install Ollama and pull models (all safe on 8GB RAM)
# https://ollama.com
ollama pull gemma2:2b        # 1.6GB — handles classification, extraction, formatting
ollama pull llama3.2:3b      # 2.0GB — routing + medium tasks
ollama pull phi3.5:mini      # 2.2GB — reasoning + complex tasks

# 3. Collect data from your agent
python target_agent/agent.py
python tests/test_phase1_logger.py

# 4. Analyse + generate Replaceability Report
agentshrink status
agentshrink analyse

# 5. Start the dashboard
cd dashboard/backend && uvicorn main:app --port 8000 &
cd dashboard/frontend && npm install && npm run dev
# Open: http://localhost:3000

# 6. Activate ShrinkLLM in your agent
#    Change ONE word: ChatOpenAI → ShrinkLLM

# 7. Run benchmark
python benchmark/run_benchmark.py
```

## Dashboard Screens

| Screen | Route | Description |
|--------|-------|-------------|
| Overview | `/` | Call metrics, daily chart, node breakdown |
| Cluster Map | `/clusters` | Interactive UMAP scatter — click any dot to see the prompt |
| Report | `/report` | Per-cluster quality scores, recommendations, side-by-side comparisons |
| Live Routing | `/routing` | Real-time WebSocket feed of every routing decision |
| Fine-tune | `/finetune` | Colab notebook generation for borderline clusters |
| Settings | `/settings` | Thresholds, paths, model config |

## Hardware Requirements

Built and tested on **8GB RAM machine — no GPU required locally.**

| Model | RAM | Role in AgentShrink |
|-------|-----|---------------------|
| `gemma2:2b` | 1.6GB | Fast tasks: classify, extract, format |
| `llama3.2:3b` | 2.0GB | Mid tasks: routing, structured output |
| `phi3.5:mini` | 2.2GB | Deep tasks: reasoning, policy checks |

**Critical:** Set `OLLAMA_MAX_LOADED_MODELS=1` in `.env` — prevents loading two models simultaneously on 8GB machines. Fine-tuning runs on Google Colab T4 free tier.

## Test Suite

```bash
python tests/test_phase1_logger.py      # Phase 1 — logger correctness (7 tests)
python tests/test_phase2_clustering.py  # Phase 2 — clustering on synthetic data (8 tests)
python tests/test_phase3_evaluator.py   # Phase 3 — evaluator logic (8 tests, mocked)
python tests/test_phase4_router.py      # Phase 4 — routing and safety (10 tests, mocked)
```

Tests 1–7 in each file use mocks — no API calls, no Ollama, completely free.

## Paper Reference

```bibtex
@article{belcak2025slm,
  title   = {Small Language Models are the Future of Agentic AI},
  author  = {Belcak, Peter and Heinrich, Greg and Diao, Shizhe and Fu, Yonggan
             and Dong, Xin and Muralidharan, Saurav and Lin, Yingyan Celine
             and Molchanov, Pavlo},
  journal = {arXiv preprint arXiv:2506.02153},
  year    = {2025}
}
```

**Sections implemented:**
- Section 3.7 — Logging architecture (organic training data from agentic interactions)
- Section 6, S1–S6 — Complete LLM-to-SLM conversion algorithm
- Appendix B — Per-agent replaceability analysis (AgentShrink generates this automatically)

## License

MIT
