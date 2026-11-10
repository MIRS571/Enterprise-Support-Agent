"""Local auth smoke checks. Creates test conversations, never approves a refund.

Uses local bootstrap accounts from the ignored .env.local; never prints credentials.
"""
import base64
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = dict(line.split("=", 1) for line in (ROOT / "business-service/.env.local").read_text(encoding="utf-8").splitlines() if "=" in line and not line.startswith("#"))
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
checks = []


def request(path, *, token=None, body=None, headers=None, port=5175):
    sent = {"Content-Type": "application/json", **(headers or {})}
    sent["Accept"] = "text/event-stream" if path.endswith("/chat/stream") else "application/json"
    if token:
        sent["Authorization"] = "Bearer " + token
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=sent,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with OPENER.open(req, timeout=100) as response:
            text = response.read().decode()
            return response.status, text if "text/event-stream" in response.headers.get("Content-Type", "") else json.loads(text)
    except urllib.error.HTTPError as error:
        return error.code, None


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)
    print("PASS " + name, flush=True)


def login(username, password):
    code, data = request("/api/v1/auth/login", body={"username": username, "password": password})
    check("login " + username, code == 200)
    return data["access_token"]


first = login("customer1", CONFIG["AUTH_BOOTSTRAP_PASSWORD"])
second = login("customer2", CONFIG["AUTH_BOOTSTRAP_SECOND_PASSWORD"])
check("anonymous spoofed identity rejected", request("/api/v1/orders/A1001", port=8080, headers={"X-Tenant-Id": "company_001", "X-User-Id": "U1001"})[0] == 401)
code, order = request("/api/v1/orders/A1001", token=first, headers={"X-User-Id": "U2002", "X-Tenant-Id": "wrong"})
check("JWT identity overrides spoofed headers", code == 200 and order["orderId"] == "A1001")
check("other user's order hidden", request("/api/v1/orders/A1001", token=second)[0] == 404)
check("second account owns B2001", request("/api/v1/orders/B2001", token=second)[0] == 200)
check("user JWT cannot call internal API", request("/internal/v1/orders/A1001", token=first, port=8080)[0] == 401)
check("proxy does not expose internal API", request("/internal/v1/orders/A1001", token=first)[0] == 404)
code, thread = request("/api/v1/agent/threads", token=first, body={})
check("authenticated conversation created", code == 201)
tid = thread["thread_id"]
check("cross-user conversation denied", request("/api/v1/agent/chat/stream", token=second, body={"thread_id": tid, "message": "查询订单 A1001"})[0] == 404)
code, stream = request("/api/v1/agent/chat/stream", token=first, body={"thread_id": tid, "message": "查询订单 A1001"})
check("JWT to Java to Python to internal Java SSE", code == 200 and "event:result" in stream.replace("event: ", "event:") and "event:done" in stream.replace("event: ", "event:") and "event:error" not in stream.replace("event: ", "event:") and "299" in stream)
check("logout acknowledged", request("/api/v1/auth/logout", token=first, body={})[0] == 200)
check("old JWT rejected after logout", request("/api/v1/auth/me", token=first)[0] == 401)
payload = first.split(".")[1]
jti = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["jti"]
redis_env = os.environ.copy()
if CONFIG.get("BUSINESS_REDIS_PASSWORD"):
    redis_env["REDISCLI_AUTH"] = CONFIG["BUSINESS_REDIS_PASSWORD"]
ttl = int(subprocess.check_output([str(ROOT / ".local-tools/redis/redis-cli.exe"), "-h", CONFIG.get("BUSINESS_REDIS_HOST", "127.0.0.1"), "-p", CONFIG.get("BUSINESS_REDIS_PORT", "16380"), "PTTL", "esa:auth:revoked:" + jti], env=redis_env, text=True).strip())
check("blacklist real Redis TTL within token lifetime", 0 < ttl <= 3_600_000)
fresh = login("customer1", CONFIG["AUTH_BOOTSTRAP_PASSWORD"])
check("new login unaffected by old blacklist", fresh != first and request("/api/v1/auth/me", token=fresh)[0] == 200)
check("logout did not revoke other user", request("/api/v1/auth/me", token=second)[0] == 200)
request("/api/v1/auth/logout", token=fresh, body={})
request("/api/v1/auth/logout", token=second, body={})
(ROOT / ".local-run/auth-smoke-result.json").write_text(json.dumps({"passed": len(checks), "checks": checks}, indent=2), encoding="utf-8")
