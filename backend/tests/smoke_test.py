"""End-to-end smoke test against a running API (python tests/smoke_test.py).

Walks the demo on the real PostgreSQL database: sign-in by email / mobile / face with the
authenticator always second, first-time activation, account administration by role, the upload
pipeline, purpose and step-up obligations, redacted fallback, denial, share approval, §63
certificate, public MATCH/MISMATCH, and the tamper scenarios. Resets the demo data at the end.
"""

import hashlib
import json
import os
import random
import sys
import time

import httpx
import psycopg
import pyotp

API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8010/api/v1"
c = httpx.Client(base_url=API, timeout=120)
ok_count = 0
last_code: dict[str, str] = {}

OWNER_DSN = os.getenv("CFV_OWNER_DSN",
                      "host=127.0.0.1 port=5433 dbname=case_file_vault user=cfv_owner password=cfv_owner_dev")
extra_secrets: dict[str, str] = {}  # accounts activated during the test


def credentials():
    """Demo credentials exist only in the database (demo.credentials, owner-only)."""
    with psycopg.connect(OWNER_DSN) as conn:
        rows = conn.execute("""SELECT u.service_id, c.email, c.phone, c.password, c.activation_code, c.status,
                                      c.authenticator_code_now
                               FROM demo.credentials c JOIN iam.users u ON u.email = c.email""").fetchall()
    return {r[0]: dict(email=r[1], phone=r[2], password=r[3], activation_code=r[4], status=r[5], code=r[6]) for r in rows}


BY_ID = credentials()
PASSWORD = BY_ID["NV-IO-1045"]["password"]


def check(cond, label):
    global ok_count
    print(("  ✓ " if cond else "  ✗ ") + label)
    if not cond:
        sys.exit(1)
    ok_count += 1


def fresh_code(identifier):
    """Authenticator codes are single-use: wait for a step we haven't used yet."""
    for _ in range(40):
        code = (pyotp.TOTP(extra_secrets[identifier]).now() if identifier in extra_secrets
                else credentials()[identifier]["code"])
        if last_code.get(identifier) != code:
            last_code[identifier] = code
            return code
        time.sleep(1)
    raise RuntimeError("authenticator did not roll over")


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def login(sid, via="email"):
    ident = {"email": BY_ID.get(sid, {}).get("email", sid), "phone": BY_ID.get(sid, {}).get("phone", sid)}.get(via, sid)
    r = c.post("/auth/login", json={"identifier": ident, "password": PASSWORD}).json()
    tok = c.post("/auth/mfa/verify", json={"mfa_token": r["mfa_token"], "code": fresh_code(sid)}).json()
    return auth(tok["access_token"])


def face_samples(base, noise=0.02, n=4):
    return [[x + random.uniform(-noise, noise) for x in base] for _ in range(n)]


def pdf(text):
    import pymupdf
    d = pymupdf.open()
    d.new_page().insert_text((72, 72), text)
    return d.tobytes()


random.seed(26190)
check(len(BY_ID) >= 9, f"{len(BY_ID)} demo personas, read from demo.credentials (owner only)")
check(c.get("/demo/personas").status_code == 404 and c.get("/demo/totp/NV-IO-1045").status_code == 404,
      "no public endpoint reveals demo credentials or codes")

print("sign-in")
r = c.post("/auth/login", json={"identifier": "anjali.verma@nvpolice.example", "password": "wrong"})
check(r.status_code == 401, "wrong password → 401")
anjali = login("NV-IO-1045", "email")
check(c.get("/auth/me", headers=anjali).json()["service_id"] == "NV-IO-1045", "email + password + authenticator")
r = c.post("/auth/login", json={"identifier": "98100 45002", "password": PASSWORD}).json()
check(r["user"]["service_id"] == "NV-IO-1088", "mobile number accepted as identifier")
code = fresh_code("NV-IO-1088")
c.post("/auth/mfa/verify", json={"mfa_token": r["mfa_token"], "code": code})
r2 = c.post("/auth/login", json={"identifier": "98100 45002", "password": PASSWORD}).json()
r2 = c.post("/auth/mfa/verify", json={"mfa_token": r2["mfa_token"], "code": code})
check(r2.status_code == 401 and r2.json()["code"] == "OTP_REUSED", "same authenticator code refused the second time")

print("first-time activation")
r = c.post("/auth/login", json={"identifier": "pooja.thakur@nvpolice.example", "password": "anything"})
check(r.status_code == 409 and r.json()["code"] == "ACTIVATION_REQUIRED", "invited officer must activate first")
bad = c.post("/auth/activate", json={"identifier": "pooja.thakur@nvpolice.example", "activation_code": "AAAA-BBBB"})
check(bad.status_code == 401, "wrong activation code refused")
act = c.post("/auth/activate", json={"identifier": "+919810045020",
                                     "activation_code": BY_ID["NV-IO-1120"]["activation_code"]}).json()
weak = c.post("/auth/activate/password", json={"activation_token": act["activation_token"], "password": "short"})
check(weak.status_code == 422, "weak password refused")
otp = c.post("/auth/activate/password", json={"activation_token": act["activation_token"],
                                               "password": "Thakur#2026secure"}).json()
check(otp["otpauth_uri"].startswith("otpauth://totp/"), "authenticator QR issued")
extra_secrets["NV-IO-1120"] = otp["secret"]
done = c.post("/auth/activate/confirm", json={"activation_token": act["activation_token"],
                                               "code": fresh_code("NV-IO-1120")}).json()
check(done["user"]["status"] == "ACTIVE", "activated: password set, authenticator linked, signed in")

print("face sign-in")
me_face = [random.gauss(0, 0.08) for _ in range(128)]
someone_else = [random.gauss(0, 0.08) for _ in range(128)]
r = c.post("/me/face", headers=anjali, json={"samples": face_samples(me_face), "liveness": {"blink": True}})
check(r.status_code == 428 and r.json()["code"] == "STEP_UP_REQUIRED", "registering a face needs 2FA again")
c.post("/auth/step-up", headers=anjali, json={"code": fresh_code("NV-IO-1045")})
r = c.post("/me/face", headers=anjali, json={"samples": face_samples(me_face), "liveness": {"blink": False}})
check(r.status_code == 422 and r.json()["code"] == "LIVENESS_FAILED", "no blink → refused (photo attack)")
r = c.post("/me/face", headers=anjali, json={"samples": face_samples(me_face), "liveness": {"blink": True, "score": 0.97}})
check(r.status_code == 201, "face registered from Settings")
sec = c.get("/me/security", headers=anjali).json()
check(sec["face"] is not None, "settings show face sign-in enrolled")
r = c.post("/auth/login/face", json={"identifier": "anjali.verma@nvpolice.example",
                                     "samples": face_samples(someone_else), "liveness": {"blink": True}})
check(r.status_code == 401, "someone else's face refused")
r = c.post("/auth/login/face", json={"samples": face_samples(me_face), "liveness": {"blink": True}}).json()
check(r["user"]["service_id"] == "NV-IO-1045" and r["first_factor"] == "FACE", "face recognised without typing anything (1:N)")
tok = c.post("/auth/mfa/verify", json={"mfa_token": r["mfa_token"], "code": fresh_code("NV-IO-1045")}).json()
check(tok["first_factor"] == "FACE", "face + authenticator → signed in")
anjali = auth(tok["access_token"])

print("accounts by role")
neha = login("NV-ADM-001")
units = {u["code"]: u["id"] for u in c.get("/units", headers=neha).json()}
new = c.post("/users", headers=neha, json={"service_id": "NV-IO-1301", "full_name": "Kiran Bose", "rank": "ASI",
                                           "role": "INVESTIGATOR", "unit_id": units["NV-PS-RMP"],
                                           "email": "kiran.bose@nvpolice.example", "phone": "9810045031"})
check(new.status_code == 201 and len(new.json()["activation_code"]) == 9, "admin creates officer → one-time activation code")
r = c.post("/users", headers=neha, json={"service_id": "NV-ADM-002", "full_name": "Other Admin", "role": "ADMIN",
                                         "unit_id": units["NV-PS-RMP"], "email": "x@nvpolice.example", "phone": "9810045032"})
check(r.status_code == 403, "admin cannot create another admin")
check(c.get("/cases", headers=neha).json()["total"] == 0, "admin sees no cases at all")
rajeev = login("NV-SAD-001")
r = c.post("/users", headers=rajeev, json={"service_id": "NV-ADM-002", "full_name": "Arvind Kulkarni", "role": "ADMIN",
                                           "unit_id": units["NV-DHQ-NVG"], "email": "arvind.k@nvpolice.example", "phone": "9810045033"})
check(r.status_code == 201, "super admin creates an admin")
roles = c.get("/roles", headers=rajeev).json()
check([x["code"] for x in roles][:2] == ["SUPER_ADMIN", "ADMIN"], "roles come from iam.roles")

print("dashboard & cases")
dash = c.get("/dashboard/summary", headers=anjali).json()
check(len(dash["kpis"]) == 4, "investigator docket")
hero = c.get("/cases", params={"q": "0142"}, headers=anjali).json()["items"][0]
check(hero["case_number"] == "NV/SHN/0142/2026", "hero case found")
docs = {d["title"]: d for d in c.get(f"/cases/{hero['id']}/documents", headers=anjali).json()["items"]}
vs = docs["Statement of V-1"]

print("upload pipeline")
data = pdf("Statement of witness WS-3: the white SUV NV 01 AB 4521 was seen again near the bus stand.")
sha = hashlib.sha256(data).hexdigest()
bad = c.post(f"/cases/{hero['id']}/documents", headers=anjali, files={"file": ("ws3.pdf", data, "application/pdf")},
             data={"metadata": json.dumps({"title": "WS-3", "doc_type": "WITNESS_STATEMENT", "client_sha256": "0" * 64})})
check(bad.status_code == 422 and bad.json()["code"] == "HASH_MISMATCH", "tampered-in-transit upload rejected")
up = c.post(f"/cases/{hero['id']}/documents", headers=anjali, files={"file": ("ws3.pdf", data, "application/pdf")},
            data={"metadata": json.dumps({"title": "Witness statement WS-3 (bus conductor)",
                                          "doc_type": "WITNESS_STATEMENT", "client_sha256": sha})})
check(up.status_code == 202, "upload accepted (202)")
for _ in range(60):
    p = c.get(f"/versions/{up.json()['version_id']}/processing", headers=anjali).json()
    if p["status"] in ("READY", "FAILED", "QUARANTINED"):
        break
    time.sleep(0.5)
check(p["status"] == "READY", "pipeline READY on PostgreSQL")

print("access obligations")
r = c.post(f"/versions/{vs['current_version']['id']}/access", headers=anjali, json={"variant": "ORIGINAL", "disposition": "inline"})
check(r.status_code == 428 and r.json()["code"] == "PURPOSE_REQUIRED", "victim original needs purpose (428)")
r = c.post(f"/versions/{vs['current_version']['id']}/access", headers=anjali,
           json={"variant": "ORIGINAL", "disposition": "inline", "purpose": "Preparing for court hearing"})
check(r.status_code == 200 and c.get(r.json()["url"].replace("/api/v1", "")).content.startswith(b"%PDF"), "original streams with purpose")
rohit = login("NV-IO-1088", "phone")
r = c.post(f"/versions/{vs['current_version']['id']}/access", headers=rohit, json={"variant": "ORIGINAL", "disposition": "inline"})
check(r.json()["variant"] == "REDACTED", "co-IO gets the redacted copy")

print("denial, search, sharing")
arjun = login("NV-IO-2210")
r = c.get(f"/cases/{hero['id']}", headers=arjun)
check(r.status_code == 403 and r.json()["deny_reason"] == "NOT_A_CASE_MEMBER", "outsider denied (403)")
s = c.get("/search", params={"q": "white SUV near bus stand"}, headers=anjali).json()
check(any("WS-1" in h["document"]["title"] for h in s["items"]), "Postgres full-text search finds WS-1")
s = c.get("/search", params={"q": "vehical", "mode": "fuzzy"}, headers=anjali).json()
check(s["total"] > 0, "trigram fuzzy search tolerates a typo")
ws1 = docs["Witness statement WS-1 (shopkeeper)"]
farhan_id = c.get("/directory", params={"q": "Farhan"}, headers=anjali).json()[0]["id"]
req = c.post(f"/documents/{ws1['id']}/shares", headers=anjali,
             json={"grantee_user_id": farhan_id, "scope": "VIEW", "expires_at": "2026-10-12T00:00:00Z",
                   "reason": "Trial preparation for hearing"}).json()
check(c.post(f"/requests/{req['id']}/decision", headers=anjali, json={"decision": "APPROVE"}).status_code == 403, "self-approval denied")
meera = login("NV-SHO-201")
check(c.post(f"/requests/{req['id']}/decision", headers=meera, json={"decision": "APPROVE"}).json()["status"] == "APPROVED", "supervisor approved")

print("certificate & verification")
cert = c.post(f"/versions/{ws1['current_version']['id']}/certificates", headers=anjali,
              json={"signatory_name": "Meera Nair", "signatory_designation": "Inspector (SHO)"}).json()
code = cert["verification_code"]
check(c.post(f"/public/verify/{code}", json={"sha256": ws1["current_version"]["sha256"]}).json()["result"] == "MATCH", "public MATCH")
check(c.post(f"/public/verify/{code}", json={"sha256": "a" * 64}).json()["result"] == "MISMATCH", "public MISMATCH")
check(c.post(f"/versions/{ws1['current_version']['id']}/verify", headers=anjali).json()["overall"] == "VERIFIED", "document verifies")

print("tamper lab (super admin)")
suresh = login("NV-AUD-009")
check(c.post("/audit/verify-chain", headers=suresh).json()["status"] == "VALID", "chain VALID")
t2 = c.post("/demo/tamper", headers=rajeev, json={"scenario": "T2_OVERWRITE_STORED_OBJECT", "version_id": ws1["current_version"]["id"]}).json()
check(t2["executed"] is False, "T2 overwrite refused")
c.post("/demo/tamper", headers=rajeev, json={"scenario": "T5_REPLACE_CIPHERTEXT", "version_id": ws1["current_version"]["id"]})
check(c.post(f"/versions/{ws1['current_version']['id']}/verify", headers=anjali).json()["overall"] == "FAILED", "T5 ciphertext tamper caught")
c.post("/demo/tamper", headers=rajeev, json={"scenario": "T3_EDIT_AUDIT_ROW", "seq": 300})
r = c.post("/audit/verify-chain", headers=suresh).json()
check(r["status"] == "BROKEN" and r["first_break"]["seq"] == 300, f"T3 rogue-DBA edit → broken at #300 ({r['first_break']['check']})")

print("reset")
check(c.post("/demo/reset", headers=rajeev).status_code == 204, "demo reset (schema rebuilt from migrations)")
BY_ID.update(credentials())
rajeev = login("NV-SAD-001")
suresh = login("NV-AUD-009")
check(c.post("/audit/verify-chain", headers=suresh).json()["status"] == "VALID", "chain VALID after reset")
c.post("/demo/tamper", headers=rajeev, json={"scenario": "T4_REWRITE_AUDIT_CHAIN", "seq": 120})
r = c.post("/audit/verify-chain", headers=suresh).json()
check(r["status"] == "BROKEN" and r["first_break"]["check"].startswith("CHECKPOINT"),
      f"T4 full rewrite → caught by sealed checkpoint ({r['first_break']['check']})")
c.post("/demo/reset", headers=rajeev)
print(f"\nall {ok_count} checks passed")
