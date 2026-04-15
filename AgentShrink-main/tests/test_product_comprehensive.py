"""
Comprehensive AgentShrink Product Test Suite
Tests all backend endpoints, gateway, and frontend pages
"""
import sys
import json
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8000"
GW = "http://localhost:8100"
FE = "http://localhost:3000"

results = []

def test(name, url, method="GET", data=None, expect_status=200, headers=None):
    try:
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        resp = urllib.request.urlopen(req, timeout=10)
        status = resp.status
        ok = status == expect_status
        results.append((name, "PASS" if ok else f"FAIL (got {status})", url))
        return ok
    except urllib.error.HTTPError as e:
        ok = e.code == expect_status
        results.append((name, "PASS" if ok else f"FAIL (got {e.code})", url))
        return ok
    except Exception as e:
        results.append((name, f"ERROR ({e.__class__.__name__})", url))
        return False

print("=" * 70)
print("AGENTSHRINK COMPREHENSIVE PRODUCT TEST")
print("=" * 70)

# ── Gateway Tests ──
print("\n[GATEWAY]")
test("Gateway /health", f"{GW}/health")
test("Gateway reject no auth", f"{GW}/v1/chat/completions", "POST",
     {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
     expect_status=401)

# ── Core Pipeline ──
print("\n[CORE PIPELINE]")
test("GET /api/status", f"{BASE}/api/status")
test("GET /api/dashboard/summary", f"{BASE}/api/dashboard/summary")
test("GET /api/clusters", f"{BASE}/api/clusters")
test("GET /api/report", f"{BASE}/api/report")
test("GET /api/analysis/logs", f"{BASE}/api/analysis/logs")

# ── Routing ──
print("\n[ROUTING]")
test("GET /api/routing/stats", f"{BASE}/api/routing/stats")
test("GET /api/routing/simulate", f"{BASE}/api/routing/simulate")
test("GET /api/gateway/activity", f"{BASE}/api/gateway/activity")

# ── Product Config ──
print("\n[PRODUCT CONFIG]")
test("GET /api/config", f"{BASE}/api/config")
test("GET /api/product/config", f"{BASE}/api/product/config")
test("GET /api/product/doctor", f"{BASE}/api/product/doctor")
test("GET /api/product/stack", f"{BASE}/api/product/stack")
test("GET /api/product/logs?service=gateway", f"{BASE}/api/product/logs?service=gateway&stream=stdout&lines=20")

# ── Provider Registry ──
print("\n[PROVIDERS]")
test("GET /api/product/providers", f"{BASE}/api/product/providers")
test("GET /api/product/provider-presets", f"{BASE}/api/product/provider-presets")

# ── Models ──
print("\n[MODELS]")
test("GET /api/models", f"{BASE}/api/models")

# ── Fine-tune ──
print("\n[FINETUNE]")
test("GET /api/finetune/backends", f"{BASE}/api/finetune/backends")
test("GET /api/finetune/jobs", f"{BASE}/api/finetune/jobs")

# ── Public/Auth ──
print("\n[PUBLIC/AUTH]")
test("GET /api/public/identity", f"{BASE}/api/public/identity")
test("GET /api/public/session", f"{BASE}/api/public/session")
test("GET /api/public/auth/providers", f"{BASE}/api/public/auth/providers")
test("GET /api/public/projects", f"{BASE}/api/public/projects")
test("GET /api/public/teams", f"{BASE}/api/public/teams")
test("GET /api/public/invites", f"{BASE}/api/public/invites")
test("GET /api/public/billing", f"{BASE}/api/public/billing")
test("GET /api/public/hosted/config", f"{BASE}/api/public/hosted/config")

# ── Frontend Pages ──
print("\n[FRONTEND PAGES]")
pages = [
    ("/", "Overview"),
    ("/welcome", "Welcome"),
    ("/auth", "Auth"),
    ("/account", "Account"),
    ("/teams", "Teams"),
    ("/projects", "Projects"),
    ("/billing", "Billing"),
    ("/clusters", "Clusters"),
    ("/report", "Report"),
    ("/routing", "Routing"),
    ("/finetune", "Fine-tune"),
    ("/models", "Models"),
    ("/settings", "Settings"),
    ("/site", "Site Landing"),
    ("/site/docs", "Site Docs"),
]
for path, name in pages:
    test(f"Frontend {name}", f"{FE}{path}")

# ── Summary ──
print("\n" + "=" * 70)
passed = sum(1 for _, s, _ in results if s == "PASS")
failed = sum(1 for _, s, _ in results if s != "PASS")
print(f"RESULTS: {passed} passed, {failed} failed, {len(results)} total")
print("=" * 70)

for name, status, url in results:
    icon = "OK" if status == "PASS" else "XX"
    print(f"  [{icon}] {name}: {status}")

if failed:
    print(f"\n  FAILURES:")
    for name, status, url in results:
        if status != "PASS":
            print(f"    [XX] {name}: {status} -> {url}")

sys.exit(0 if failed == 0 else 1)
