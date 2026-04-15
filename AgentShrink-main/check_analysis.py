"""Quick check of analysis results after bulk prompt run."""
import requests
import json

BASE = "http://localhost:8000"

# Dashboard summary
r = requests.get(f"{BASE}/api/summary")
s = r.json()
print("=== DASHBOARD SUMMARY ===")
print(f"  Total calls: {s.get('total_calls', 0)}")
print(f"  Has data: {s.get('has_data')}")
print(f"  Analysis done: {s.get('analysis_done')}")
print(f"  Report done: {s.get('report_done')}")
print(f"  Gateway events: {s.get('gateway_event_count', 0)}")

# Clusters
r = requests.get(f"{BASE}/api/clusters")
c = r.json()
print(f"\n=== CLUSTERS ===")
print(f"  Cluster count: {c.get('n_clusters', 0)}")
print(f"  Total points: {len(c.get('points', []))}")
if c.get("clusters"):
    for cid, info in list(c["clusters"].items())[:8]:
        name = info.get("cluster_name", "?")
        size = info.get("size", 0)
        print(f"  [{cid}] {name} ({size} prompts)")

# Report
r = requests.get(f"{BASE}/api/report")
rpt = r.json()
clusters_list = rpt.get("clusters", [])
print(f"\n=== REPORT (Replaceability) ===")
print(f"  Total clusters: {len(clusters_list)}")

ft = [c for c in clusters_list if c.get("recommendation") == "fine_tune"]
rn = [c for c in clusters_list if c.get("recommendation") == "replace_now"]
kl = [c for c in clusters_list if c.get("recommendation") == "keep_llm"]

print(f"  Replace-now:  {len(rn)}")
print(f"  Fine-tune:    {len(ft)}")
print(f"  Keep-LLM:     {len(kl)}")

if ft:
    print(f"\n  Fine-tune candidates:")
    for c in ft[:10]:
        score = c.get("best_score", 0)
        size = c.get("cluster_size", 0)
        base = c.get("fine_tune_base_model", "?")
        print(f"    - {c.get('cluster_name')}: score={score:.2f}, size={size}, base={base}")

if rn:
    print(f"\n  Replace-now clusters:")
    for c in rn[:5]:
        print(f"    - {c.get('cluster_name')}: score={c.get('best_score', 0):.2f}, size={c.get('cluster_size', 0)}")

# Fine-tune backends
r = requests.get(f"{BASE}/api/finetune/backends")
b = r.json()
print(f"\n=== FINE-TUNE BACKENDS ===")
for be in b.get("backends", []):
    status = "ready" if be.get("configured") else "not configured"
    print(f"  {be['id']:15s} | {be['label']:30s} | {status}")

# Fine-tune jobs
r = requests.get(f"{BASE}/api/finetune/jobs")
j = r.json()
jobs = j.get("jobs", [])
print(f"\n=== FINE-TUNE JOBS ===")
print(f"  Total jobs: {len(jobs)}")
for job in jobs[:5]:
    print(f"  [{job.get('status')}] {job.get('cluster_name', '?')} on {job.get('backend', '?')}")

print("\n=== DONE ===")
