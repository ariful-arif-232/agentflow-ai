"""Prototype security safeguards: server-side acknowledgement, replay guard, rate limiting, tamper-evident audit."""
import json
import warnings

import pytest

warnings.filterwarnings("ignore", category=DeprecationWarning)
from fastapi.testclient import TestClient  # noqa: E402

from app import audit as audit_mod  # noqa: E402
from app import security  # noqa: E402
from app.audit import AuditChain, fingerprint, verify_chain  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _rid(client, i=0):
    return client.get("/api/rebalancing/recommendations").json()["recommendations"][i]["id"]


# ------------------------------------------------------------------ server-side acknowledgement
def test_direct_api_calls_cannot_bypass_acknowledgement(client):
    rid = _rid(client)
    before = len(client.get("/api/rebalancing/audit").json()["simulations"])
    missing = client.post("/api/rebalancing/simulate", json={"recommendation_ids": [rid]})
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "validation_error"
    false = client.post("/api/rebalancing/simulate", json={"recommendation_ids": [rid], "reviewer_acknowledged": False})
    assert false.status_code == 400 and "acknowledgement" in false.json()["error"]["message"]
    for loose in ("yes", "true", 1):  # strict boolean: no coercion of strings or numbers
        r = client.post("/api/rebalancing/simulate", json={"recommendation_ids": [rid], "reviewer_acknowledged": loose})
        assert r.status_code == 422
    mp = client.post("/api/morning-plan/simulate", json={"date": "2026-08-27", "reviewer_acknowledged": False})
    assert mp.status_code == 400  # Morning Plan keeps its server-side acknowledgement
    assert len(client.get("/api/rebalancing/audit").json()["simulations"]) == before  # rejected calls wrote nothing


def test_acknowledged_approval_is_simulation_only_and_hash_chained(client):
    rid = _rid(client, 1)
    r = client.post("/api/rebalancing/simulate", json={"recommendation_ids": [rid], "reviewer_acknowledged": True})
    assert r.status_code == 200
    j = r.json()
    assert j["simulation_only"] is True and j["status"].startswith("SIMULATED") and j["reviewer_acknowledged"] is True
    assert len(j["record_hash"]) == 64 and len(j["previous_hash"]) == 64 and j["kind"] == "intraday_rebalancing"
    integrity = client.get("/api/rebalancing/audit").json()["integrity"]
    assert integrity["verified"] is True and integrity["tamper_evident"] is True
    assert "not tamper-proof" in integrity["note"]


# ------------------------------------------------------------------ replay guard
def test_duplicate_approval_does_not_create_a_second_record(client):
    rid = _rid(client, 2)
    body = {"recommendation_ids": [rid], "reviewer_acknowledged": True, "reviewer_note": "first"}
    a = client.post("/api/rebalancing/simulate", json=body).json()
    n = len(client.get("/api/rebalancing/audit").json()["simulations"])
    b = client.post("/api/rebalancing/simulate", json={**body, "reviewer_note": "double click"}).json()
    assert a["replayed"] is False and b["replayed"] is True
    assert b["simulation_id"] == a["simulation_id"] and b["record_hash"] == a["record_hash"]
    assert len(client.get("/api/rebalancing/audit").json()["simulations"]) == n
    # duplicate ids inside one request are collapsed; order does not matter
    c = client.post("/api/rebalancing/simulate", json={**body, "recommendation_ids": [rid, rid]}).json()
    assert c["replayed"] is True
    m1 = client.post("/api/morning-plan/simulate", json={"date": "2026-08-26", "reviewer_acknowledged": True}).json()
    m2 = client.post("/api/morning-plan/simulate", json={"date": "2026-08-26", "reviewer_acknowledged": True}).json()
    assert m2["replayed"] is True and m2["simulation_id"] == m1["simulation_id"] and m2["money_moved"] is False


def test_fingerprint_is_deterministic_and_order_independent():
    assert fingerprint({"a": 1, "b": [1, 2]}) == fingerprint({"b": [1, 2], "a": 1})
    assert fingerprint({"a": 1}) != fingerprint({"a": 2})


# ------------------------------------------------------------------ rate limiting
def test_rate_limiter_sliding_window():
    now = [0.0]
    lim = security.RateLimiter(security.RateLimitConfig(max_requests=3, window_seconds=10), clock=lambda: now[0])
    assert [lim.check("s", "c")[0] for _ in range(3)] == [True, True, True]
    ok, retry = lim.check("s", "c")
    assert not ok and 1 <= retry <= 10
    assert lim.check("s", "other-client")[0] and lim.check("other-scope", "c")[0]  # keyed per client and scope
    now[0] = 10.5
    assert lim.check("s", "c")[0]
    off = security.RateLimiter(security.RateLimitConfig(max_requests=0))
    assert all(off.check("s", "c")[0] for _ in range(50))


def test_rate_limit_config_validation_and_proxy_trust():
    assert security.config_from_env({}) == security.RateLimitConfig()
    cfg = security.config_from_env({"AGENTFLOW_RATE_LIMIT_SIMULATIONS": "5", "AGENTFLOW_RATE_LIMIT_WINDOW_SECONDS": "30"})
    assert (cfg.max_requests, cfg.window_seconds) == (5, 30.0)
    for env in ({"AGENTFLOW_RATE_LIMIT_SIMULATIONS": "many"}, {"AGENTFLOW_RATE_LIMIT_SIMULATIONS": "-1"},
                {"AGENTFLOW_RATE_LIMIT_WINDOW_SECONDS": "0"}):
        with pytest.raises(ValueError):
            security.config_from_env(env)
    untrusted = security.RateLimiter(security.RateLimitConfig())
    assert untrusted.client_key("10.0.0.1", "1.2.3.4") == "10.0.0.1"  # spoofable header ignored by default
    trusted = security.RateLimiter(security.RateLimitConfig(trust_forwarded_for=True))
    assert trusted.client_key("10.0.0.1", "1.2.3.4, 10.0.0.1") == "1.2.3.4"


def test_simulation_endpoints_return_429_but_reads_are_not_limited(client, monkeypatch):
    monkeypatch.setattr(security, "_limiter", security.RateLimiter(security.RateLimitConfig(max_requests=2, window_seconds=60)))
    rid = _rid(client, 3)
    body = {"recommendation_ids": [rid], "reviewer_acknowledged": True}
    codes = [client.post("/api/rebalancing/simulate", json=body).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    r = client.post("/api/rebalancing/simulate", json=body)
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["Retry-After"]) >= 1 and "Prototype process-local" in r.json()["error"]["message"]
    assert client.post("/api/morning-plan/simulate", json={"date": "2026-08-25", "reviewer_acknowledged": True}).status_code == 200
    assert all(client.get(u).status_code == 200 for u in ["/api/overview", "/api/rebalancing/recommendations", "/api/impact"] * 5)
    assert client.get("/api/security/status").json()["rate_limit"]["max_requests"] == 2


# ------------------------------------------------------------------ tamper-evident audit
def _chain_with(n, path=None):
    ch = AuditChain(path)
    for i in range(n):
        ch.append("intraday_rebalancing", {"simulation_id": f"SIM-{i}", "total_amount": 1000.0 * i, "reviewer_note": None},
                  fingerprint({"i": i}))
    return ch


def test_valid_chain_verifies_and_preserves_order():
    ch = _chain_with(5)
    recs = list(reversed(ch.entries()))
    assert [r["sequence"] for r in recs] == [1, 2, 3, 4, 5]
    assert recs[0]["previous_hash"] == audit_mod.GENESIS_HASH
    assert all(recs[i]["previous_hash"] == recs[i - 1]["record_hash"] for i in range(1, 5))
    assert ch.verify()["verified"] and ch.writable


@pytest.mark.parametrize("tamper", ["edit", "delete", "reorder", "rehash_one"])
def test_tampering_breaks_verification(tamper):
    recs = list(reversed(_chain_with(5).entries()))
    if tamper == "edit":
        recs[2]["total_amount"] = 999_999.0
    elif tamper == "delete":
        del recs[2]
    elif tamper == "reorder":
        recs[1], recs[2] = recs[2], recs[1]
    else:  # recompute one record's own hash after editing it: its successor no longer links
        recs[2]["reviewer_note"] = "changed"
        recs[2]["record_hash"] = audit_mod.record_hash(recs[2])
    res = verify_chain(recs)
    assert not res["verified"] and res["first_bad_sequence"] is not None


def test_in_memory_tampering_fails_closed(client, monkeypatch):
    ch = _chain_with(3)
    ch._records[1]["total_amount"] = 1.0  # simulate in-process tampering
    assert not ch.writable
    monkeypatch.setattr(audit_mod, "_chain", ch)
    r = client.post("/api/rebalancing/simulate", json={"recommendation_ids": [_rid(client)], "reviewer_acknowledged": True})
    assert r.status_code == 503 and r.json()["error"]["code"] == "audit_unavailable"


def test_optional_jsonl_audit_reloads_and_verifies(tmp_path):
    path = tmp_path / "audit" / "simulations.jsonl"
    ch = _chain_with(4, path)
    lines = path.read_text().splitlines()
    assert len(lines) == 4 and json.loads(lines[-1])["record_hash"] == ch.entries()[0]["record_hash"]
    again = AuditChain(path)  # restart: reload + verify
    assert again.verify()["verified"] and len(again.entries()) == 4 and again.writable
    assert again.find(fingerprint({"i": 2}))["simulation_id"] == "SIM-2"  # replay guard survives restart
    rec, created = again.append("morning_plan", {"simulation_id": "MLP-X"}, fingerprint({"i": "new"}))
    assert created and rec["sequence"] == 5 and rec["previous_hash"] == json.loads(lines[-1])["record_hash"]
    tampered = [json.loads(x) for x in path.read_text().splitlines()]
    tampered[1]["total_amount"] = 123.0
    path.write_text("\n".join(json.dumps(x) for x in tampered) + "\n")
    bad = AuditChain(path)
    assert not bad.verify()["verified"] and not bad.writable and "failed verification" in bad.status()["reason"]
    path.write_text(path.read_text() + "{not json\n")
    assert not AuditChain(path).writable


def test_security_status_is_read_only_and_honest(client):
    s = client.get("/api/security/status").json()
    assert s["approval"]["server_enforced_acknowledgement"] and s["approval"]["money_moved"] is False
    assert "not enterprise IAM" in s["label"] and "Not implemented" in s["authentication"]
    assert "never labelled fraud" in s["manipulation_guardrail"]
    assert client.post("/api/security/status").status_code == 405
    assert "secret" not in json.dumps(s).lower() and "token" not in json.dumps(s).lower()


def test_frontend_sends_acknowledgement_and_labels_prototype_controls():
    from pathlib import Path
    web = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"
    reb = (web / "app" / "rebalancing" / "page.tsx").read_text()
    assert "reviewer_acknowledged: ack" in reb and "disabled={!ack || busy}" in reb  # sent only after the checkbox
    sec = (web / "components" / "SecurityPosture.tsx").read_text()
    for phrase in ("Implemented now", "Prototype safeguards", "Still required for production", "not enterprise IAM",
                   "Anomaly ≠ fraud", "never automatically rewarded with liquidity", "Not an enterprise WAF",
                   "not implemented", "no money moves"):
        assert phrase in sec, phrase
    rai = (web / "app" / "responsible-ai" / "page.tsx").read_text()
    assert "<SecurityPosture />" in rai and "Anomaly ≠ fraud" in rai
    for src in (reb, sec, rai):
        low = src.lower()
        assert "production-grade" not in low and "bank-grade" not in low and "fraud detected" not in low
    assert "NEXT_PUBLIC_" not in sec  # no backend secret is exposed to the browser
