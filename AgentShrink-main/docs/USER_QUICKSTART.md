# AgentShrink Quickstart

## 1. Initialize the local project

```powershell
agentshrink init --project-name "My AgentShrink Project"
agentshrink doctor
```

## 2. Start the local stack

Use the one-command foreground supervisor:

```powershell
agentshrink stack up
```

Keep that terminal open while you use the product.

If you need to inspect or stop it later:

```powershell
agentshrink stack status
agentshrink stack down
```

## 3. Point your app at the gateway

### OpenAI-compatible client

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8100/v1",
    api_key="agentshrink-local",
)
```

### Raw HTTP app

```python
import requests

response = requests.post(
    "http://127.0.0.1:8100/v1/chat/completions",
    headers={"Authorization": "Bearer agentshrink-local"},
    json={
        "model": "mock-model",
        "messages": [{"role": "user", "content": "hello"}],
    },
)
```

## 4. Open the dashboard

- `http://localhost:3000/welcome`
- `http://localhost:3000/routing`
- `http://localhost:3000/clusters`
- `http://localhost:3000/report`

## 5. Free local test mode

By default, `agentshrink init` and `agentshrink start gateway` use `mock` upstream mode.

That means you can:
- test integration
- verify the dashboard
- verify logging
- verify gateway behavior

without spending money on real providers.

## 6. Canonical first-run path

If you are not sure what to do first, always use this order:

1. `agentshrink init`
2. `agentshrink doctor`
3. `agentshrink stack up`
4. open `/welcome`
5. copy the integration snippet for your app
6. send traffic through the gateway
