# AgentShrink Product Roadmap

This roadmap reflects the repo as it exists today, not just the original plan.
It is organized as:

- `Done`: already implemented in the repo
- `In Progress`: partially implemented or working but not fully polished
- `Next`: the highest-value product work to build next

The current product direction is:

> product hardening and trust UX, not raw infrastructure

That means the biggest wins now are making AgentShrink easier to trust, easier to operate, and easier for a new user to adopt without hand-holding.

## v0.2 - Local Developer Product

Goal: a new user can clone the repo, initialize a project, start services, and point an AI app at the AgentShrink gateway.

### Done
- `agentshrink init`
- `agentshrink doctor`
- `agentshrink start gateway`
- `agentshrink start backend`
- `agentshrink start frontend`
- OpenAI-compatible gateway
- upstream provider support in the gateway for:
  - `mock`
  - `openai`
  - `nvidia`
  - `ollama`
  - `huggingface`
- local dashboard reading from a chosen SQLite DB
- local tracing core shared by:
  - callback logging
  - OpenAI wrapper logging
  - gateway logging
- example gateway integrations:
  - OpenAI Agents SDK
  - raw HTTP app
  - plain `OpenAI(base_url=..., api_key=...)` client flow

### In Progress
- install story is still repo-first rather than polished package-first
- some flows still assume local developer context
- docs are much better, but not yet fully streamlined into one canonical first-run path

## v0.5 - Team-Friendly Product

Goal: reduce manual config and make the repo feel like a coherent tool, not just a collection of modules.

### Done
- project-based onboarding wizard in the dashboard
- one-command local stack launcher:
  - `agentshrink stack up`
  - `agentshrink stack status`
  - `agentshrink stack down`
- saved integration snippets on the Welcome page for:
  - OpenAI SDK
  - raw HTTP
- in-app `Test My Gateway` flow
- stack health visibility in the onboarding page
- clearer product docs and quickstart structure

### In Progress
- cleaner model/provider setup validation
- stronger onboarding flow for new users
- more consistent dashboard UX across all pages
- better explanation of routing state and next steps

### Still Missing
- project manifest editing from the UI
- richer provider credential validation and error guidance

## v0.6 - Product Hardening

Goal: make AgentShrink feel trustworthy, operable, and smooth enough that a new user can succeed without repo spelunking.

### Done
- editable settings UI
  - project name
  - ports
  - DB path
  - output directory
  - gateway defaults
- stack controls and logs in the app
  - recent service log tails
  - clearer service health diagnostics
- LangChain/LangGraph onboarding snippet
  - logger mode
  - routed `ShrinkLLM` mode
- provider setup validation
  - API key presence checks
  - Ollama reachability checks
  - Hugging Face token/gated-access checks where relevant
- routing simulation and rollback basics
  - dry-run routing preview
  - “what would happen” view before apply
  - rollback to previous routing config

### In Progress
- stack controls in app are guidance-first rather than full in-browser process execution
- provider validation is substantially better, but still not a full guided credential setup flow
- safer stack actions now exist as recommended state-aware commands, but not full in-browser process control
- routing explainability is stronger in report/simulation, but can still become richer in live routing views

### Next
- richer provider credential validation and error guidance
- safer stack actions if we can make them trustworthy on Windows
- stronger explainability around why a route was proposed or changed

### Why This Is Next
The repo already has enough infrastructure to demonstrate the core idea.
The biggest gap is now trust and usability:

- users need to understand what AgentShrink is doing
- users need safer controls before changing routing behavior
- users need clearer setup guidance when providers or local models are misconfigured

That is why the next milestone is product hardening, not more low-level plumbing.

## v1.0 - Public Product

Goal: make AgentShrink usable by external teams with minimal setup and a hosted experience.

### Done
- first real public-product slice started:
  - public landing page at `/site`
  - public docs page at `/site/docs`
- project-token-oriented gateway contract:
  - hosted-style snippets now speak in terms of a project token
  - project token rotation from the product UI/backend
- gateway auth boundary groundwork:
  - OpenAI-compatible gateway can enforce a Bearer project token
  - tests now cover token-required and token-valid flows

### In Progress
- public landing/docs exist, but are still served from the local app shell rather than a separate hosted deployment
- project token support exists, but team/account separation does not yet exist behind it
- the hosted/public contract is now real, but billing, auth, and multi-tenant isolation are not yet implemented

### Next
- hosted deployment of landing site and docs
- hosted dashboard / account system
- project tokens and team/project separation
- hosted gateway option
- local connector for Ollama / on-device routing
- rollback and simulation mode polished into a full trust layer
- packaged installers and a real `pip install agentshrink` path

### Notes
This milestone should start only after local product hardening is strong enough.
The hosted version will be much easier to build well once the local product flow is stable, explainable, and trusted.

## v1.1 - Provider-Agnostic Gateway

Goal: evolve AgentShrink from a few built-in upstreams into a provider-agnostic gateway with adapter registry + BYOK config.

### Done
- provider registry + BYOK settings UI exists
- custom `openai_compatible` providers can be saved and used as gateway upstreams
- judge/evaluation path now reuses registry-backed provider clients for OpenAI-compatible providers like Sarvam

### In Progress
- adapter surface is still small:
  - `mock`
  - `openai_compatible`
  - `huggingface_chat`
- gateway, doctor checks, and settings are not yet broad enough for major non-OpenAI-native providers

### Next
- add first-class native adapters:
  - `gemini_native`
  - `anthropic_native`
  - `azure_openai`
- add preset provider entries on top of adapters:
  - Gemini
  - OpenRouter
  - Azure OpenAI
- add provider connection testing in Settings
- add model discovery for saved providers where the upstream supports it
- add generic `custom_http` as the long-tail escape hatch for nonstandard APIs

### Rollout Plan
1. Land one native adapter end to end.
   Start with Gemini because the repo already has Google SDK support.
2. Make adapter support consistent across:
   - gateway
   - provider doctor checks
   - judge/evaluator
   - settings UI
3. Add provider presets for common endpoints built on shared adapters.
4. Add provider connection test + model discovery UX.
5. Add `custom_http` for long-tail vendor coverage.

## Summary

### Done
- v0.2 is largely complete
- meaningful parts of v0.5 are already built

### In Progress
- onboarding polish
- provider validation
- better UI consistency and usability
- first hosted/public-product groundwork has started

### Next
- continue v0.6 product hardening:
  - richer provider credential validation and guidance
  - safer stack actions
  - stronger routing explainability
- continue v1.0 with:
  - hosted deployment shape
  - account/project separation
  - hosted gateway option
- continue v1.1 with:
  - native provider adapters
  - provider presets
  - connection testing and model discovery
