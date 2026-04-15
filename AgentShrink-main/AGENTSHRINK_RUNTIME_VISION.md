# AgentShrink Runtime Vision

## What AgentShrink Is Becoming

AgentShrink should evolve from:

- an analyzer of past LLM calls

into:

- a shared inference control layer for enterprise agents

That means it will do two jobs:

1. Offline intelligence
   - observe calls
   - cluster task patterns
   - evaluate candidate models
   - learn routing policy
2. Online execution
   - receive live task requests
   - decide which model should handle each task
   - execute the call
   - log the outcome
   - improve future routing

AgentShrink is not just a dashboard or report generator. It becomes the runtime brain between agents and models.

## The Core Enterprise Setup

In a company setting, you usually have:

- internal agents
- enterprise API keys
- access to multiple providers/models
- control over the agent runtime
- multiple surfaces like VS Code, web apps, and internal tools

This works well for AgentShrink if the company owns the agent code or backend. If that is true, every model call can be forced through AgentShrink.

Instead of:

```python
response = nvidia_llm.invoke(messages)
```

the goal is:

```python
response = agentshrink.invoke(
    workflow="case_agent",
    node="classify_customer_message",
    messages=messages,
)
```

That lets AgentShrink:

- log the request
- identify the task type
- choose the cheapest acceptable model
- call it
- fallback if needed
- log response, tokens, and latency

## The Multi-Model Pattern

The common pattern is:

1. Orchestrator
   - receives the user request
   - breaks it into sub-tasks
   - decides workflow shape
2. Specialists
   - individual models do the work they are best suited for
3. Composer
   - merges specialist outputs into a final answer

AgentShrink fits underneath that pattern.

The runtime becomes:

1. Orchestrator
2. AgentShrink runtime
3. Specialist models
4. Composer

The orchestrator decides what task should happen.

AgentShrink decides which model should do it.

## Offline Intelligence

Offline, AgentShrink should:

1. Ingest model call logs
   - messages
   - system prompt
   - tools
   - response
   - tokens
   - latency
   - provider/model
   - app/workflow/node metadata
2. Curate the logs
3. Create embeddings
4. Cluster similar tasks
5. Build representative samples per cluster
   - some prompts near centroid
   - some prompts from the edges
6. Evaluate all enabled models per cluster
7. Produce a routing policy

The routing policy should answer:

- which models are acceptable for each cluster
- which one is the cheapest among passing candidates
- what fallback to use if routing confidence is low

## Online Execution

Online, AgentShrink should:

1. Receive a live task request
2. Normalize the request context
   - app
   - workflow
   - node
   - system
   - messages
   - tools
3. Route the task
   - embed the task
   - find the nearest cluster
   - compute routing confidence
   - choose the best model from routing config
   - fallback if confidence is low
4. Execute the provider call
5. Return the result
6. Log the full outcome for future learning

This creates a loop:

- observe
- learn
- route
- observe again

## Why Wrapper-Level Logging Matters

The real ingestion strategy should be:

- every model call in company-owned agents goes through an AgentShrink wrapper or gateway

This is the control point.

It gives:

- request
- response
- latency
- tokens
- provider/model
- task metadata
- routing decision

That is much better than scraping surfaces like browser UIs.

## Wrapper vs Gateway

There are two good implementation forms.

### 1. SDK / Library Wrapper

Best first step.

Each internal agent imports AgentShrink directly.

Pros:

- fastest to build
- easiest to integrate into the current repo
- best when we own the agent code

Cons:

- logic is embedded in each app
- consistency can drift if adoption is uneven

### 2. Central Gateway Service

Best long-term architecture.

All agents call one internal service and that service is AgentShrink.

Pros:

- centralized logging
- centralized routing
- easier policy rollout
- consistent behavior across apps

Cons:

- more infra and operational work

Best path:

1. start as an SDK
2. mature into a gateway

## How VS Code Fits

VS Code should be treated as a frontend surface, not the routing system itself.

The strong integration model is:

1. VS Code is the UI
2. internal agent runtime does the orchestration
3. AgentShrink sits inside that runtime and controls model calls

That same runtime can serve:

- VS Code
- web apps
- internal support tools
- automation jobs

## How Multi-Model Selection Works

The selection logic should be:

1. There are many candidate models
   - local Ollama models
   - NVIDIA-hosted models
   - later OpenAI, Claude, Gemini, and others
2. Each cluster is evaluated against all enabled models
3. Each model gets a score for that cluster
   - quality / evaluation score
   - latency
   - cost
4. At runtime, for a new task:
   - match it to a cluster
   - if confidence is high, look up evaluated candidates
   - filter by passing threshold
   - choose the most cost-effective acceptable model
   - if confidence is low, send to strong fallback model

The runtime decision should not be:

- always use model X

It should be:

- for this task family, use the cheapest model that has already proven good enough

## Example Workflow

Consider a case-handling agent with nodes:

- classify
- extract fields
- decide policy
- draft response
- format output

With AgentShrink:

- `classify` might route to a tiny local model
- `extract` might route to a small local or cheap remote model
- `decide_policy` might route to a stronger reasoning model
- `draft_response` might route to a writing-optimized model
- `format_output` might route to a cheap deterministic model

The orchestrator still runs the workflow.

AgentShrink selects the model for each node.

## Current Repo Direction

This repo already has pieces of the future system:

- logging in `agentshrink/logger.py`
- runtime routing in `agentshrink/shrink_llm.py`
- model catalog in `agentshrink/model_catalog.py`
- provider helpers in `agentshrink/provider_clients.py`
- evaluation in `agentshrink/evaluator.py`
- clustering in `agentshrink/clusterer.py`
- target-agent examples in `target_agent/`

What is still missing is the productized runtime boundary:

- one standard invocation API every internal agent must use

## Target Architecture

The future architecture should include:

1. ingestion
   - normalized logging of all calls
2. router
   - cluster matching
   - confidence checks
   - model selection
3. executor
   - provider-specific invocation
   - retries
   - fallbacks
4. policy store
   - routing config
   - thresholds
   - model eligibility
5. analysis
   - clustering
   - evaluation
   - reporting
6. runtime API
   - library or service entry point for agent apps
7. dashboard
   - model catalog
   - clusters
   - reports
   - live traffic

## Practical Roadmap

1. Normalize runtime invocation
   - create one shared `invoke()` or `get_routed_llm()` interface
2. Force target agents to use it
   - remove scattered direct provider calls
3. Improve logging schema
   - app, workflow, node, session, trace, route decision
4. Finalize routing policy usage
   - runtime always reads routing config
5. Make fallback behavior explicit
   - low confidence
   - unsupported task
   - model failure
   - policy violation
6. Expose as a service later
   - after the SDK path is stable

## Bottom Line

AgentShrink should become:

- an enterprise model gateway
- a workload observer
- a multi-model router
- a cost optimizer
- a quality-preserving execution layer

The end-state is:

- every internal agent uses AgentShrink to invoke models
- AgentShrink logs all calls
- AgentShrink learns the best model per task family
- AgentShrink routes live calls accordingly
- AgentShrink keeps improving from real traffic over time
