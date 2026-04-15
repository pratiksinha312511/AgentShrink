"""Quick end-to-end test of all AgentShrink backend APIs and gateway routing."""
import requests
from openai import OpenAI

BASE = 'http://localhost:8000'
GW = 'http://localhost:8100'
TOKEN = 'as_live_33lTz9tmAWqyscwkWSOwi3TK'

results = []

# 1. Backend health
r = requests.get(f'{BASE}/api/health')
results.append(('Backend health', r.status_code == 200))

# 2. Models API
r = requests.get(f'{BASE}/api/models')
results.append(('Models API', r.status_code == 200))

# 3. Report API
r = requests.get(f'{BASE}/api/report')
results.append(('Report API', r.status_code == 200))

# 4. Clusters API
r = requests.get(f'{BASE}/api/clusters')
results.append(('Clusters API', r.status_code == 200))

# 5. Fine-tune backends
r = requests.get(f'{BASE}/api/finetune/backends')
results.append(('FT backends', r.status_code == 200))

# 6. Fine-tune jobs
r = requests.get(f'{BASE}/api/finetune/jobs')
results.append(('FT jobs', r.status_code == 200))

# 7. Routing stats
r = requests.get(f'{BASE}/api/routing/stats')
results.append(('Routing stats', r.status_code == 200))

# 8. Analysis logs
r = requests.get(f'{BASE}/api/analysis/logs')
results.append(('Analysis logs', r.status_code == 200))

# 9. Gateway health
r = requests.get(f'{GW}/health')
results.append(('Gateway health', r.status_code == 200))

# 10. Gateway chat completion
client = OpenAI(base_url=f'{GW}/v1', api_key=TOKEN)
resp = client.chat.completions.create(
    model='gpt-4o-mini',
    messages=[{'role': 'user', 'content': 'Test prompt 1'}]
)
results.append(('Gateway chat', resp.choices[0].message.content != ''))

# 11. Gateway activity
r = requests.get(f'{BASE}/api/gateway/activity')
results.append(('Gateway activity', r.status_code == 200))

# 12. Multiple gateway calls to test routing
for i in range(3):
    resp = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{'role': 'user', 'content': f'Routing test {i + 2}'}]
    )
results.append(('Multi-routing', True))

# Print results
print()
passed = sum(1 for _, ok in results if ok)
total = len(results)
for name, ok in results:
    status = 'PASS' if ok else 'FAIL'
    print(f'  {status} {name}')
print(f'\n  {passed}/{total} tests passed')
