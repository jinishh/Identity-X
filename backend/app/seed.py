"""Fictional seed world (docs/06-demo-story.md). Every person, place, phone and vehicle number
here is invented. Documents are generated as real PDFs/PNGs and pushed through the real
pipeline, so every hash, signature, ciphertext and audit link is genuine.

Run:  python -m app.seed          (wipes data/ and rebuilds)
"""

import hashlib
import io
import json
import os
import random
import shutil
from datetime import date, datetime, timedelta

import pyotp
from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from sqlalchemy import select

from . import audit, config, crypto, integrity, migrate, models, pipeline, policy, security
from .audit import Ctx
from .db import SessionLocal, engine
from .models import (ActivationCode, Alert, Case, CaseMember, DemoPersona, Document, DocumentVersion,
                     Permission, Request, Role, RolePermission, Share, SigningKey, TotpCredential, Unit,
                     User, new_id)

# Demo login for every seeded account (local demo data only). 2FA codes are shown by the
# demo authenticator on the login page while DEMO_MODE is on.
DEMO_PASSWORD = config.DEMO_PASSWORD

rng = random.Random(26190)
START = datetime(2026, 6, 1, 4, 30)  # history replay begins (UTC)


# ───────────── clock ─────────────

class Clock:
    def __init__(self, t: datetime):
        self.t = t

    def at(self, t: datetime):
        # Never go backwards: audit sequence order must equal time order.
        self.t = max(t, self.t + timedelta(minutes=1))
        models.clock_override = self.t

    def tick(self, minutes: float = 7):
        self.at(self.t + timedelta(minutes=minutes))


# ───────────── generated files ─────────────

def make_pdf(title: str, meta: list[tuple[str, str]], paragraphs: list[str],
             footer: str = "") -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    L, R = 20 * mm, W - 20 * mm
    y = H - 20 * mm

    def header():
        nonlocal y
        c.setFillColor(colors.HexColor("#1e2a4a"))
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(W / 2, H - 14 * mm, "NAVAGARH STATE POLICE")
        c.setFont("Helvetica", 8)
        c.drawCentredString(W / 2, H - 18 * mm, "(fictional — SIH 2026 demonstration data)")
        c.setStrokeColor(colors.HexColor("#1e2a4a"))
        c.line(L, H - 21 * mm, R, H - 21 * mm)
        y = H - 30 * mm

    header()
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(L, y, title)
    y -= 9 * mm
    for k, v in meta:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(L, y, k)
        c.setFont("Helvetica", 9)
        c.drawString(L + 45 * mm, y, v)
        y -= 5.2 * mm
    y -= 4 * mm
    for para in paragraphs:
        words, line = para.split(), ""
        c.setFont("Helvetica", 10)
        for w in words:
            trial = f"{line} {w}".strip()
            if c.stringWidth(trial, "Helvetica", 10) > R - L:
                c.drawString(L, y, line)
                y -= 5.4 * mm
                line = w
                if y < 30 * mm:
                    c.showPage()
                    header()
                    c.setFont("Helvetica", 10)
            else:
                line = trial
        if line:
            c.drawString(L, y, line)
            y -= 5.4 * mm
        y -= 3 * mm
        if y < 30 * mm:
            c.showPage()
            header()
    if footer:
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(colors.HexColor("#5b6478"))
        c.drawString(L, 15 * mm, footer)
    c.showPage()
    c.save()
    return buf.getvalue()


def make_cctv_png(label: str) -> bytes:
    img = Image.new("RGB", (960, 540), (24, 28, 34))
    d = ImageDraw.Draw(img)
    for i in range(0, 540, 4):
        d.line([(0, i), (960, i)], fill=(30 + (i % 12), 34, 40))
    d.polygon([(0, 540), (380, 250), (580, 250), (960, 540)], fill=(52, 56, 60))
    d.rectangle([90, 120, 300, 330], outline=(120, 120, 110), width=3)       # bus shelter
    d.text((110, 135), "BUS STAND", fill=(170, 170, 150))
    d.rounded_rectangle([520, 300, 760, 410], 18, fill=(225, 225, 220))      # white SUV
    d.rectangle([545, 315, 735, 350], fill=(60, 70, 80))
    d.ellipse([545, 385, 600, 440], fill=(15, 15, 15))
    d.ellipse([680, 385, 735, 440], fill=(15, 15, 15))
    d.rectangle([600, 392, 680, 408], fill=(250, 250, 240))
    d.text((606, 394), "NV01AB4521", fill=(10, 10, 10))
    d.rectangle([0, 0, 960, 28], fill=(0, 0, 0))
    d.text((10, 8), label, fill=(80, 255, 120))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


EICAR = (b"%PDF-1.4\n% EICAR test payload follows\n"
         b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*\n%%EOF\n")


# ───────────── world ─────────────

UNITS = [
    ("NV-HQ", "Navagarh State Police HQ", "STATE_HQ", None),
    ("NV-DHQ-NVG", "Navagarh District HQ", "DISTRICT_HQ", "NV-HQ"),
    ("NV-PS-SHN", "Shantinagar Police Station", "POLICE_STATION", "NV-DHQ-NVG"),
    ("NV-PS-MPN", "Mahila Police Station, Navagarh", "POLICE_STATION", "NV-DHQ-NVG"),
    ("NV-PS-RMP", "Rampur Police Station", "POLICE_STATION", "NV-DHQ-NVG"),
    ("NV-FSL-01", "Navagarh Regional FSL", "FSL", "NV-HQ"),
    ("NV-PRO-01", "Navagarh Prosecution Office", "PROSECUTION_OFFICE", "NV-HQ"),
    ("NV-NCRB-AUD", "NCRB Audit Cell", "NCRB_CELL", "NV-HQ"),
]

CAST = [  # service_id, name, rank, role, unit, email, mobile
    ("NV-SAD-001", "Rajeev Menon", "Additional DGP (Technical Services)", "SUPER_ADMIN", "NV-HQ", "rajeev.menon@nvpolice.example", "+919810045000"),
    ("NV-ADM-001", "Neha Joshi", "District System Administrator", "ADMIN", "NV-DHQ-NVG", "neha.joshi@nvpolice.example", "+919810045008"),
    ("NV-IO-1045", "Anjali Verma", "Sub-Inspector", "INVESTIGATOR", "NV-PS-SHN", "anjali.verma@nvpolice.example", "+919810045001"),
    ("NV-IO-1088", "Rohit Kumar", "ASI", "INVESTIGATOR", "NV-PS-SHN", "rohit.kumar@nvpolice.example", "+919810045002"),
    ("NV-SHO-201", "Meera Nair", "Inspector (SHO)", "SUPERVISOR", "NV-PS-SHN", "meera.nair@nvpolice.example", "+919810045003"),
    ("NV-DSP-031", "Vikram Rao", "DSP", "SUPERVISOR", "NV-DHQ-NVG", "vikram.rao@nvpolice.example", "+919810045004"),
    ("NV-APP-077", "Farhan Siddiqui", "Assistant Public Prosecutor", "PROSECUTOR", "NV-PRO-01", "farhan.siddiqui@nvpolice.example", "+919810045005"),
    ("NV-FSL-512", "Dr. Kavya Iyer", "Scientific Officer", "FORENSIC_EXPERT", "NV-FSL-01", "kavya.iyer@nvpolice.example", "+919810045006"),
    ("NV-AUD-009", "Suresh Patil", "Audit Officer", "AUDITOR", "NV-NCRB-AUD", "suresh.patil@nvpolice.example", "+919810045007"),
    ("NV-IO-2210", "Arjun Mehta", "Sub-Inspector", "INVESTIGATOR", "NV-PS-RMP", "arjun.mehta@nvpolice.example", "+919810045009"),
    ("NV-IO-1102", "Sunil Yadav", "Sub-Inspector", "INVESTIGATOR", "NV-PS-MPN", "sunil.yadav@nvpolice.example", "+919810045010"),
    ("NV-IO-2231", "Priyanka Das", "Inspector", "INVESTIGATOR", "NV-PS-RMP", "priyanka.das@nvpolice.example", "+919810045011"),
    ("NV-SHO-202", "Rekha Pillai", "Inspector (SHO)", "SUPERVISOR", "NV-PS-MPN", "rekha.pillai@nvpolice.example", "+919810045012"),
    ("NV-SHO-203", "Manoj Tiwari", "Inspector (SHO)", "SUPERVISOR", "NV-PS-RMP", "manoj.tiwari@nvpolice.example", "+919810045013"),
]
# A new officer the admin has created but who hasn't signed in yet — for the activation demo.
INVITED = ("NV-IO-1120", "Pooja Thakur", "Sub-Inspector", "INVESTIGATOR", "NV-PS-SHN",
           "pooja.thakur@nvpolice.example", "+919810045020")
INVITED_CODE = "SHN4-7KQ2"

PERSONAS = [  # service_id, headline, what it shows
    ("NV-IO-1045", "Lead IO on the bus-stand case",
     "Uploading evidence, stating a purpose to open a victim record, requesting a share, issuing a §63 certificate"),
    ("NV-IO-1088", "Co-IO on the same case",
     "Gets the redacted copy of victim records automatically — no name, address or phone"),
    ("NV-SHO-201", "SHO, Shantinagar",
     "Approving shares and charge-sheets, watching alerts for her station"),
    ("NV-APP-077", "Prosecutor for the trial",
     "Hearings, documents shared for trial, placing evidence on legal hold"),
    ("NV-FSL-512", "Scientific officer, FSL",
     "Accepting custody of the seized phone and filing the forensic report"),
    ("NV-AUD-009", "NCRB audit cell",
     "Verifying the whole audit chain and every file — without ever seeing document content"),
    ("NV-ADM-001", "District administrator",
     "Creating officer accounts and handing out activation codes — no access to any case"),
    ("NV-SAD-001", "Super administrator, State HQ",
     "Managing administrators and units, and running the tamper lab"),
    ("NV-IO-2210", "IO at a different station",
     "Trying to open a case that isn't his, and being refused on the record"),
    ("NV-IO-1120", "New officer, not activated yet",
     "First-time sign-in: activation code from the admin, set a password, link the authenticator"),
]

VICTIM = {"name": "Nisha Rawat", "address": "House 14, Gulmohar Colony",
          "phone": "98765 01234", "aadhaar": "4821 7730 1956"}


class World:
    def __init__(self, db, clock):
        self.db, self.clock = db, clock
        self.units: dict[str, Unit] = {}
        self.users: dict[str, User] = {}
        self.secrets: dict[str, str] = {}

    def ctx(self, sid: str | None) -> Ctx:
        return Ctx(user=self.users[sid] if sid else None, ip="10.20.4.17",
                   user_agent="Mozilla/5.0 (seed)")

    # ── cases ──
    def case(self, sid, station, fir_no, fir_date, title, category, sections, status,
             members=(), victim=None, hearing=None, court=None, description=None):
        db, lead = self.db, self.users[sid]
        unit = self.units[station]
        victim_protected = category in ("CRIME_AGAINST_WOMEN", "CRIME_AGAINST_CHILDREN")
        c = Case(id=new_id(), fir_number=fir_no, fir_date=fir_date, unit_id=unit.id,
                 case_number=f"NV/{station.split('-')[-1]}/{fir_no.split('/')[0]}/{fir_no.split('/')[1]}",
                 title=title, category=category, offence_sections=sections, status="REGISTERED",
                 is_victim_protected=victim_protected,
                 victim_pseudonym="V-1" if victim_protected else None,
                 victim_identifiers_enc=crypto.seal(json.dumps(victim).encode()) if victim else None,
                 default_sensitivity="VICTIM_PROTECTED" if victim_protected else "CONFIDENTIAL",
                 lead_io_id=lead.id, created_by=lead.id, next_hearing_date=hearing,
                 court_name=court, description=description)
        db.add(c)
        db.add(CaseMember(case_id=c.id, user_id=lead.id, capacity="LEAD_IO", added_by=lead.id))
        audit.record(db, self.ctx(sid), "CASE_CREATED", f"Registered {c.case_number}: {title}",
                     case_id=c.id, details={"category": category,
                                            "victim_protected": victim_protected})
        for msid, cap in members:
            self.clock.tick(rng.randint(20, 240))
            u = self.users[msid]
            db.add(CaseMember(case_id=c.id, user_id=u.id, capacity=cap, added_by=lead.id))
            audit.record(db, self.ctx(sid), "CASE_MEMBER_ADDED", f"Added {u.full_name} as {cap}",
                         case_id=c.id, target_user_id=u.id, details={"capacity": cap})
        path = ["REGISTERED", "UNDER_INVESTIGATION", "CHARGESHEET_FILED", "UNDER_TRIAL",
                "DISPOSED", "CLOSED"]
        if status == "FINAL_REPORT_FILED":
            path = ["REGISTERED", "UNDER_INVESTIGATION", "FINAL_REPORT_FILED"]
        for s in path[1:path.index(status) + 1] if status != "REGISTERED" else []:
            self.clock.tick(rng.randint(60, 600))
            old, c.status = c.status, s
            audit.record(db, self.ctx(sid), "CASE_STATUS_CHANGED", f"{c.case_number}: {old} → {s}",
                         case_id=c.id, details={"from": old, "to": s})
        return c

    # ── documents ──
    def upload(self, sid, case, title, doc_type, data, filename, sensitivity=None,
               existing: Document | None = None, note=None) -> Document:
        db = self.db
        from .routers.cases import next_doc_number
        doc = existing or Document(
            id=new_id(), doc_number=next_doc_number(db), case_id=case.id, title=title,
            doc_type=doc_type, sensitivity=sensitivity or case.default_sensitivity,
            custodian_id=self.users[sid].id, created_by=self.users[sid].id)
        v = pipeline.intake(db, self.ctx(sid), doc, data, filename, crypto.sha256_hex(data),
                            note, is_new=existing is None)
        db.commit()
        self.clock.tick(0.2)
        pipeline.run(v.id, delay_ms=0)
        db.expire_all()
        return db.get(Document, doc.id)

    def view(self, sid, doc: Document, purpose=None, download=False, redacted=False):
        action = "REDACTED_VIEWED" if redacted else ("DOCUMENT_DOWNLOADED" if download else "DOCUMENT_VIEWED")
        verb = {"REDACTED_VIEWED": "Viewed redacted copy of", "DOCUMENT_DOWNLOADED": "Downloaded",
                "DOCUMENT_VIEWED": "Viewed"}[action]
        v = self.db.get(DocumentVersion, doc.current_version_id)
        audit.record(self.db, self.ctx(sid), action, f"{verb} {doc.title} (v{v.version_no})",
                     case_id=doc.case_id, document_id=doc.id, version_id=v.id, purpose=purpose,
                     details={"variant": "REDACTED" if redacted else "ORIGINAL"})

    def request(self, sid, rtype, doc, reason, payload, assigned_to=None, version_id=None) -> Request:
        r = Request(id=new_id(), type=rtype, case_id=doc.case_id, document_id=doc.id,
                    version_id=version_id, requested_by=self.users[sid].id,
                    assigned_to=self.users[assigned_to].id if assigned_to else None,
                    reason=reason, payload=payload)
        self.db.add(r)
        audit.record(self.db, self.ctx(sid), "REQUEST_CREATED",
                     f"Requested {rtype.replace('_', ' ').lower()} for {doc.doc_number}",
                     case_id=doc.case_id, document_id=doc.id, request_id=r.id)
        return r

    def decide(self, sid, r: Request, approve=True, note=None):
        r.status = "APPROVED" if approve else "REJECTED"
        r.decided_by, r.decided_at, r.decision_note = self.users[sid].id, models.utcnow(), note
        audit.record(self.db, self.ctx(sid), f"REQUEST_{r.status}",
                     f"{r.status.title()} {r.type.replace('_', ' ').lower()} request",
                     case_id=r.case_id, document_id=r.document_id, request_id=r.id,
                     details={"note": note})


def _units_and_users(w: World):
    db = w.db
    for code, name, utype, parent in UNITS:
        u = Unit(id=new_id(), code=code, name=name, type=utype,
                 parent_id=w.units[parent].id if parent else None, district="Navagarh",
                 state="Navagarh (fictional)")
        db.add(u)
        w.units[code] = u
    for code, title, tier, administrative, sees, desc in policy.ROLES:
        db.add(Role(code=code, title=title, tier=tier, is_administrative=administrative,
                    sees_case_content=sees, description=desc))
    for code, desc in policy.PERMISSIONS.items():
        db.add(Permission(code=code, description=desc))
    db.flush()
    for role, perms in policy.SYSTEM_PERMISSIONS.items():
        for p in perms:
            db.add(RolePermission(role_code=role, permission_code=p))
    db.flush()
    pw = security.hash_password(DEMO_PASSWORD)
    creator = None
    for sid, name, rank, role, unit, email, phone in CAST:
        u = User(id=new_id(), service_id=sid, full_name=name, rank=rank, role=role,
                 unit_id=w.units[unit].id, email=email, phone=phone, password_hash=pw,
                 status="ACTIVE", activated_at=w.clock.t, created_by=creator.id if creator else None)
        db.add(u)
        db.flush()
        secret = pyotp.random_base32()
        db.add(TotpCredential(user_id=u.id, secret_enc=crypto.seal(secret.encode()), confirmed_at=w.clock.t))
        w.secrets[sid] = secret
        w.users[sid] = u
        creator = creator or u  # the super admin "created" everyone else
    sid, name, rank, role, unit, email, phone = INVITED
    invited = User(id=new_id(), service_id=sid, full_name=name, rank=rank, role=role,
                   unit_id=w.units[unit].id, email=email, phone=phone, status="INVITED",
                   created_by=w.users["NV-ADM-001"].id)
    db.add(invited)
    db.flush()
    db.add(ActivationCode(user_id=invited.id, issued_by=w.users["NV-ADM-001"].id,
                          code_hash=hashlib.sha256(INVITED_CODE.encode()).hexdigest(),
                          expires_at=datetime(2026, 12, 31)))
    w.users[sid] = invited
    for i, (sid, headline, shows) in enumerate(PERSONAS):
        db.add(DemoPersona(user_id=w.users[sid].id, sort=i, headline=headline, shows=shows,
                           activation_code=INVITED_CODE if sid == INVITED[0] else None,
                           demo_password=DEMO_PASSWORD if sid != INVITED[0] else None,
                           totp_secret=w.secrets.get(sid)))
    for purpose, kid in crypto.SIGNING_KEY_IDS.items():
        db.add(SigningKey(id=kid, purpose=purpose, public_key=crypto.public_key_bytes(purpose)))
    db.commit()
    for sid in w.users:
        db.refresh(w.users[sid])


def _hero(w: World):
    """NV/SHN/0142/2026 — stalking and assault, victim-protected (BNS 74, 78, 351(2))."""
    clock, db = w.clock, w.db
    clock.at(datetime(2026, 8, 14, 5, 40))
    c = w.case("NV-IO-1045", "NV-PS-SHN", "0142/2026", date(2026, 8, 14),
               "Stalking and assault near Shantinagar bus stand", "CRIME_AGAINST_WOMEN",
               ["BNS 74", "BNS 78", "BNS 351(2)"], "UNDER_INVESTIGATION",
               members=[("NV-IO-1088", "CO_IO")], victim=[VICTIM["name"], VICTIM["address"]],
               description="Complainant (V-1) reports being followed for several weeks and "
                           "assaulted on 12 Aug 2026 near the bus stand.")
    hero_meta = [("FIR No.", "0142/2026"), ("Police Station", "Shantinagar"),
                 ("District", "Navagarh"), ("Sections", "BNS 74, BNS 78, BNS 351(2)")]

    clock.tick(25)
    fir = w.upload("NV-IO-1045", c, "First Information Report — FIR 0142/2026", "FIR", make_pdf(
        "FIRST INFORMATION REPORT", hero_meta + [("Date of report", "14-08-2026, 10:55"),
                                                 ("Informant", f"Ms. {VICTIM['name']} (V-1)")],
        [f"Informant Ms. {VICTIM['name']}, resident of {VICTIM['address']}, Shantinagar, mobile "
         f"{VICTIM['phone']}, Aadhaar {VICTIM['aadhaar']}, states that for about five weeks an "
         "unknown man has been following her from the Shantinagar bus stand to her workplace.",
         "On 12-08-2026 at about 21:45 hrs, while waiting at the bus stand, the man grabbed her "
         "arm, pulled her dupatta and threatened her with harm if she informed anyone. She "
         "noticed a white SUV parked near the bus stand from which the man had stepped out.",
         "She raised an alarm; a shopkeeper nearby came forward and the man fled in the white SUV "
         "towards the Ring Road. The informant requests strict legal action.",
         "Case registered under BNS 74, BNS 78 and BNS 351(2). Investigation entrusted to "
         "SI Anjali Verma (NV-IO-1045)."],
        "Read over and admitted correct. Signature of informant obtained."), "fir_0142_2026.pdf")

    clock.tick(180)
    vs = w.upload("NV-IO-1045", c, "Statement of V-1", "VICTIM_STATEMENT", make_pdf(
        "STATEMENT OF THE VICTIM (recorded at residence)", hero_meta + [("Recorded on", "15-08-2026")],
        [f"I, {VICTIM['name']}, aged 24, residing at {VICTIM['address']}, Shantinagar, state that "
         "I work as a billing assistant and take the 21:30 bus from Shantinagar bus stand.",
         "Since early July the same man has been standing near the stand and following me. He is "
         "about 30 years old, medium build, with a scar on the left eyebrow. On 12-08-2026 he "
         "caught my arm and said he would harm my family if I complained.",
         f"My phone number is {VICTIM['phone']}. I can identify the man if I see him again."]),
        "victim_statement_v1.pdf")

    clock.tick(30)
    w.upload("NV-IO-1045", c, "Medical examination report", "MEDICAL_REPORT", make_pdf(
        "MEDICO-LEGAL EXAMINATION REPORT", hero_meta + [("Hospital", "District Hospital, Navagarh")],
        [f"Examined Ms. {VICTIM['name']} on 15-08-2026 at 14:10 hrs at the request of SI Anjali "
         "Verma. Contusion 4 cm x 2 cm on the right forearm, consistent with forcible grip, "
         "approximately 48-72 hours old. No other injuries.",
         "Opinion: injury simple in nature, caused by blunt force."]), "mlc_report.pdf")

    clock.at(datetime(2026, 8, 16, 6, 20))
    ws1 = w.upload("NV-IO-1088", c, "Witness statement WS-1 (shopkeeper)", "WITNESS_STATEMENT", make_pdf(
        "STATEMENT OF WITNESS (WS-1)", hero_meta + [("Witness", "Shri Ramesh Gupta, shopkeeper")],
        ["I run a tea stall facing the Shantinagar bus stand. On 11-08-2026 at around 21:45 hrs "
         "I heard a woman shout and saw a man pulling her by the arm.",
         "A white SUV was parked near the bus stand, close to my stall, with its engine running. "
         "The man ran back to the white SUV and drove towards the Ring Road. I saw the number "
         "plate partly: NV 01 AB 45..",
         "I have seen the same white SUV near the bus stand on several evenings in the last month."],
        ), "ws1_shopkeeper.pdf", sensitivity="CONFIDENTIAL")
    clock.tick(26 * 60)
    ws1 = w.upload("NV-IO-1088", c, ws1.title, "WITNESS_STATEMENT", make_pdf(
        "STATEMENT OF WITNESS (WS-1) — corrected", hero_meta + [("Witness", "Shri Ramesh Gupta, shopkeeper")],
        ["I run a tea stall facing the Shantinagar bus stand. On 12-08-2026 at around 21:45 hrs "
         "I heard a woman shout and saw a man pulling her by the arm.",
         "A white SUV was parked near the bus stand, close to my stall, with its engine running. "
         "The man ran back to the white SUV and drove towards the Ring Road. I saw the number "
         "plate partly: NV 01 AB 45..",
         "I have seen the same white SUV near the bus stand on several evenings in the last month.",
         "Correction: the incident date is 12-08-2026, not 11-08-2026 as earlier recorded."]),
        "ws1_shopkeeper_corrected.pdf", existing=ws1, note="Corrected incident date to 12-08-2026")

    clock.tick(200)
    w.upload("NV-IO-1088", c, "Witness statement WS-2 (auto driver)", "WITNESS_STATEMENT", make_pdf(
        "STATEMENT OF WITNESS (WS-2)", hero_meta + [("Witness", "Shri Mahesh Kale, auto-rickshaw driver")],
        ["On 12-08-2026 around 21:50 hrs a white SUV, registration NV 01 AB 4521, overtook my auto "
         "near the Ring Road crossing at high speed. I noted the number because it nearly hit me.",
         "The driver was a man of about 30 years. I can identify the vehicle."]),
        "ws2_auto_driver.pdf", sensitivity="CONFIDENTIAL")

    clock.tick(90)
    cctv = w.upload("NV-IO-1045", c, "CCTV still — bus stand camera 3", "CCTV_STILL",
                    make_cctv_png("CAM-03  SHANTINAGAR BUS STAND  12-08-2026 21:47:13"),
                    "cam03_2147.png", sensitivity="CONFIDENTIAL")

    clock.at(datetime(2026, 8, 21, 9, 15))
    seizure = w.upload("NV-IO-1045", c, "Seizure memo — accused's mobile phone", "SEIZURE_MEMO", make_pdf(
        "SEIZURE MEMO", hero_meta + [("Seized on", "21-08-2026, 14:30"), ("Place", "Ring Road, Navagarh")],
        ["Vehicle NV 01 AB 4521 (white SUV) was traced to accused Shri Deepak Solanki, aged 31. "
         "One mobile phone (black, IMEI ending 4410) was seized from the accused in the presence "
         "of two independent witnesses, sealed in envelope S-1 and marked for FSL examination."]),
        "seizure_memo_phone.pdf", sensitivity="RESTRICTED")

    clock.tick(40)
    w.view("NV-IO-1045", fir, purpose="Preparing seizure memo and accused identification")
    clock.tick(15)
    w.view("NV-IO-1088", vs, redacted=True)

    # custody of the seizure memo → FSL
    clock.at(datetime(2026, 8, 22, 5, 0))
    db.add(CaseMember(case_id=c.id, user_id=w.users["NV-FSL-512"].id, capacity="FORENSIC",
                      added_by=w.users["NV-IO-1045"].id, expires_at=datetime(2026, 11, 30)))
    audit.record(db, w.ctx("NV-IO-1045"), "CASE_MEMBER_ADDED", "Added Dr. Kavya Iyer as FORENSIC",
                 case_id=c.id, target_user_id=w.users["NV-FSL-512"].id,
                 details={"capacity": "FORENSIC"})
    clock.tick(10)
    r = w.request("NV-IO-1045", "CUSTODY_TRANSFER", seizure,
                  "Sealed phone (S-1) sent to FSL for data extraction",
                  {"from_user_id": w.users["NV-IO-1045"].id, "to_user_id": w.users["NV-FSL-512"].id},
                  assigned_to="NV-FSL-512")
    clock.tick(150)
    w.decide("NV-FSL-512", r)
    seizure.custodian_id = w.users["NV-FSL-512"].id
    audit.record(db, w.ctx("NV-FSL-512"), "CUSTODY_TRANSFERRED",
                 f"Custody of {seizure.doc_number}: Anjali Verma → Dr. Kavya Iyer",
                 case_id=c.id, document_id=seizure.id, request_id=r.id,
                 details={"from": "NV-IO-1045", "to": "NV-FSL-512"})

    clock.at(datetime(2026, 9, 2, 8, 0))
    w.upload("NV-FSL-512", c, "Forensic report — phone extraction", "FORENSIC_REPORT", make_pdf(
        "FORENSIC EXAMINATION REPORT — FSL/NVG/2026/0871", hero_meta + [("Exhibit", "S-1 (mobile phone)")],
        ["The seal of envelope S-1 was found intact. A logical extraction was performed. "
         "Extraction image SHA-256: 3f1c…9be2 (full value in annexure).",
         "The gallery contains 23 photographs of the Shantinagar bus stand taken between 05-07-2026 "
         "and 11-08-2026 between 21:00 and 22:00 hrs. Location history places the device near the "
         "bus stand on 19 evenings in this period, including 12-08-2026 at 21:41-21:52 hrs."]),
        "fsl_report_0871.pdf", sensitivity="RESTRICTED")

    # charge-sheet: v1 returned, v2 approved
    clock.at(datetime(2026, 9, 12, 6, 30))
    cs_text = [
        "Accused: Shri Deepak Solanki, aged 31, owner of white SUV NV 01 AB 4521.",
        f"Victim: V-1 ({VICTIM['name']}). Offences under BNS 74, BNS 78 and BNS 351(2) are made out "
        "on the basis of the FIR, statement of V-1, WS-1, WS-2, CCTV still CAM-03, the seizure memo "
        "and the FSL report FSL/NVG/2026/0871.",
    ]
    cs = w.upload("NV-IO-1045", c, "Charge-sheet (final report under BNSS 193)", "CHARGESHEET",
                  make_pdf("CHARGE-SHEET — DRAFT", hero_meta, cs_text), "chargesheet_draft_v1.pdf")
    v1 = db.get(DocumentVersion, cs.current_version_id)
    v1.review_status = "RETURNED"
    rv = w.request("NV-IO-1045", "REVIEW", cs, "Draft charge-sheet for review",
                   {"version_no": 1}, version_id=v1.id)
    clock.tick(300)
    w.decide("NV-SHO-201", rv, approve=False, note="Attach the FSL location-history findings.")
    clock.at(datetime(2026, 9, 15, 7, 10))
    cs = w.upload("NV-IO-1045", c, cs.title, "CHARGESHEET", make_pdf(
        "CHARGE-SHEET", hero_meta, cs_text + [
            "FSL report records the accused's device near the bus stand on 19 evenings, including "
            "the time of the incident."]),
        "chargesheet_v2.pdf", existing=cs, note="Added FSL location-history findings")
    v2 = db.get(DocumentVersion, cs.current_version_id)
    rv2 = w.request("NV-IO-1045", "REVIEW", cs, "Revised as advised", {"version_no": 2},
                    version_id=v2.id)
    clock.tick(120)
    w.decide("NV-SHO-201", rv2, note="Approved for filing.")
    v2.review_status = "APPROVED"
    clock.tick(30)
    c.status = "CHARGESHEET_FILED"
    c.court_name, c.next_hearing_date = "Sessions Court, Navagarh", date(2026, 10, 13)
    audit.record(db, w.ctx("NV-SHO-201"), "CASE_STATUS_CHANGED",
                 f"{c.case_number}: UNDER_INVESTIGATION → CHARGESHEET_FILED", case_id=c.id,
                 details={"from": "UNDER_INVESTIGATION", "to": "CHARGESHEET_FILED"})
    clock.tick(60)
    db.add(CaseMember(case_id=c.id, user_id=w.users["NV-APP-077"].id, capacity="PROSECUTOR",
                      added_by=w.users["NV-SHO-201"].id))
    audit.record(db, w.ctx("NV-SHO-201"), "CASE_MEMBER_ADDED", "Added Farhan Siddiqui as PROSECUTOR",
                 case_id=c.id, target_user_id=w.users["NV-APP-077"].id,
                 details={"capacity": "PROSECUTOR"})
    clock.tick(45)
    w.view("NV-APP-077", cs, purpose="Scrutiny of charge-sheet before trial")
    w.view("NV-APP-077", ws1)
    w.view("NV-SHO-201", cctv)
    return c


TEMPLATES = [
    ("CYBER", ["BNS 318(4)", "IT Act 66D"], "Online investment fraud via messaging app",
     ["The complainant was added to a messaging group promising high returns and transferred "
      "money to accounts controlled by the accused. Bank statements and chat exports collected."]),
    ("PROPERTY", ["BNS 305", "BNS 331(4)"], "House-breaking and theft of jewellery",
     ["Lock of the main door was found broken. Gold jewellery and cash were reported missing. "
      "Fingerprints lifted from the almirah and sent for comparison."]),
    ("BODILY_HARM", ["BNS 115(2)", "BNS 352"], "Assault after a parking dispute",
     ["The injured stated that the accused assaulted him with a wooden stick after an argument "
      "over parking outside the market. MLC obtained from the District Hospital."]),
    ("ECONOMIC", ["BNS 316(2)", "BNS 318(4)"], "Misappropriation of cooperative society funds",
     ["Audit of the society's accounts shows unexplained withdrawals over eleven months. Ledgers "
      "and cheque counterfoils have been seized."]),
    ("NARCOTICS", ["NDPS 20(b)"], "Recovery of contraband during vehicle check",
     ["During routine checking a vehicle was intercepted and contraband was recovered from the "
      "boot. Samples drawn and sealed in the presence of a gazetted officer."]),
    ("CRIME_AGAINST_WOMEN", ["BNS 85", "BNS 351(2)"], "Cruelty by husband and relatives",
     ["The complainant alleges harassment for dowry and physical cruelty by her husband and "
      "in-laws over two years. Medical records and messages produced."]),
    ("CRIME_AGAINST_WOMEN", ["BNS 78"], "Online stalking through fake social media profiles",
     ["The complainant reports repeated messages and fake profiles using her photographs. "
      "Screenshots and URLs preserved; requests sent to the platform."]),
    ("CRIME_AGAINST_CHILDREN", ["BNS 137(2)"], "Missing minor traced and recovered",
     ["A 15-year-old reported missing was traced to a bus terminal in a neighbouring district and "
      "handed over to the Child Welfare Committee."]),
    ("CYBER", ["IT Act 66C"], "SIM-swap and unauthorised UPI transfers",
     ["The complainant's mobile number was ported without consent and UPI transfers were made "
      "from her account. Telecom and bank records requested."]),
    ("PROPERTY", ["BNS 303(2)"], "Motorcycle theft from hospital parking",
     ["A motorcycle parked outside the District Hospital was stolen. CCTV footage of the parking "
      "lot is being examined."]),
]
FIRST = ["Ramesh", "Sita", "Imran", "Lakshmi", "Gurpreet", "Arun", "Fatima", "Joseph", "Meena",
         "Prakash", "Sunita", "Vijay", "Zoya", "Harish", "Kiran"]
LAST = ["Patel", "Singh", "Khan", "Menon", "Bose", "Reddy", "Thomas", "Joshi", "Chauhan", "Nair"]
STATIONS = [("NV-PS-SHN", ["NV-IO-1045", "NV-IO-1088"]), ("NV-PS-MPN", ["NV-IO-1102"]),
            ("NV-PS-RMP", ["NV-IO-2210", "NV-IO-2231"])]
STATUSES = ["REGISTERED", "UNDER_INVESTIGATION", "UNDER_INVESTIGATION", "UNDER_INVESTIGATION",
            "CHARGESHEET_FILED", "UNDER_TRIAL", "UNDER_TRIAL", "FINAL_REPORT_FILED", "CLOSED"]


def _background(w: World) -> list[Case]:
    cases = []
    fir_counter = {"NV-PS-SHN": 96, "NV-PS-MPN": 41, "NV-PS-RMP": 118}
    day = START
    for i in range(24):
        station, ios = STATIONS[i % 3]
        if i % 3 == 1 and rng.random() < 0.5:
            station, ios = "NV-PS-MPN", ["NV-IO-1102"]
        cat, sections, title, facts = TEMPLATES[i % len(TEMPLATES)]
        if station == "NV-PS-MPN" and cat not in ("CRIME_AGAINST_WOMEN", "CRIME_AGAINST_CHILDREN"):
            cat, sections, title, facts = TEMPLATES[5 + (i % 2)]
        day = max(day + timedelta(hours=rng.randint(14, 36)), w.clock.t + timedelta(hours=2))
        w.clock.at(day)
        fir_counter[station] += rng.randint(1, 4)
        fir_no = f"{fir_counter[station]:04d}/2026"
        lead = ios[i % len(ios)]
        others = [x for x in ios if x != lead]
        members = [(others[0], "CO_IO")] if others and rng.random() < 0.5 else []
        status = STATUSES[i % len(STATUSES)]
        if status in ("UNDER_TRIAL", "CHARGESHEET_FILED") and rng.random() < 0.6:
            members.append(("NV-APP-077", "PROSECUTOR"))
        complainant = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        victim = [complainant] if cat.startswith("CRIME_AGAINST") else None
        hearing = (date(2026, 10, 3) + timedelta(days=rng.randint(2, 40))
                   if status in ("UNDER_TRIAL", "CHARGESHEET_FILED") else None)
        c = w.case(lead, station, fir_no, day.date(), title, cat, sections, status, members,
                   victim=victim, hearing=hearing,
                   court="Court of the Chief Judicial Magistrate, Navagarh" if hearing else None)
        meta = [("FIR No.", fir_no), ("Police Station", w.units[station].name),
                ("Sections", ", ".join(sections))]
        w.clock.tick(rng.randint(20, 90))
        w.upload(lead, c, f"First Information Report — FIR {fir_no}", "FIR", make_pdf(
            "FIRST INFORMATION REPORT", meta + [("Complainant", complainant)],
            [f"Complainant {complainant}, mobile 9{rng.randint(100000000, 999999999)}, reports "
             "the following facts."] + facts), f"fir_{fir_no.replace('/', '_')}.pdf")
        extra = rng.randint(1, 4)
        kinds = [("WITNESS_STATEMENT", "Witness statement"), ("SEIZURE_MEMO", "Seizure memo"),
                 ("CASE_DIARY", "Case diary extract"), ("INVESTIGATION_REPORT", "Investigation report"),
                 ("MEDICAL_REPORT", "Medical report")]
        for k in range(extra):
            dtype, label = kinds[(i + k) % len(kinds)]
            w.clock.tick(rng.randint(90, 900))
            witness = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            sens = None if cat.startswith("CRIME_AGAINST") else rng.choice(
                ["CONFIDENTIAL", "CONFIDENTIAL", "RESTRICTED", "INTERNAL"])
            if sens and dtype in ("MEDICAL_REPORT", "SEIZURE_MEMO"):
                sens = "RESTRICTED"
            w.upload(rng.choice(ios), c, f"{label} — {witness}" if dtype == "WITNESS_STATEMENT" else label,
                     dtype, make_pdf(label.upper(), meta, facts + [
                         f"Recorded with reference to the statement of {witness}."]),
                     f"{dtype.lower()}_{k + 1}.pdf",
                     sensitivity=sens)
        cases.append(c)
    return cases


def _activity(w: World, hero: Case, cases: list[Case]):
    db, clock = w.db, w.clock
    clock.at(datetime(2026, 9, 24, 6, 0))
    # an EICAR upload, quarantined by the pipeline
    rmp = next(c for c in cases if c.unit_id == w.units["NV-PS-RMP"].id and c.status != "CLOSED")
    from .routers.cases import next_doc_number
    doc = Document(id=new_id(), doc_number=next_doc_number(db), case_id=rmp.id,
                   title="Bank statement (emailed attachment)", doc_type="OTHER",
                   sensitivity=rmp.default_sensitivity, custodian_id=w.users["NV-IO-2231"].id,
                   created_by=w.users["NV-IO-2231"].id)
    v = pipeline.intake(db, w.ctx("NV-IO-2231"), doc, EICAR, "bank_statement.pdf",
                        crypto.sha256_hex(EICAR), None, is_new=True)
    db.commit()
    pipeline.run(v.id, delay_ms=0)

    # Arjun (Rampur) probing the hero case: three denials → burst alert
    clock.at(datetime(2026, 9, 27, 17, 40))
    for _ in range(3):
        clock.tick(2)
        audit.record(db, w.ctx("NV-IO-2210"), "ACCESS_DENIED",
                     f"Denied case:read on {hero.case_number}", outcome="DENIED",
                     reason_code="NOT_A_CASE_MEMBER", case_id=hero.id)

    # off-hours bulk viewing on a background case
    clock.at(datetime(2026, 9, 29, 20, 10))  # 01:40 IST
    target = next(c for c in cases if c.unit_id == w.units["NV-PS-SHN"].id)
    docs = db.scalars(select(Document).where(Document.case_id == target.id)).all()
    for d_ in docs:
        clock.tick(1)
        w.view("NV-IO-1088", d_, purpose="Case review" if d_.sensitivity in ("RESTRICTED", "VICTIM_PROTECTED") else None,
               redacted=d_.sensitivity == "VICTIM_PROTECTED")
    db.add(Alert(type="OFF_HOURS_ACCESS", severity="LOW", title="Off-hours document access",
                 message=f"Rohit Kumar opened {len(docs)} documents of {target.case_number} "
                         "between 01:40 and 01:50 IST.", case_id=target.id,
                 actor_user_id=w.users["NV-IO-1088"].id, created_at=clock.t))
    db.commit()

    # pending work for the inboxes
    clock.at(datetime(2026, 9, 30, 6, 30))
    shn_docs = db.scalars(select(Document).join(Case).where(
        Case.unit_id == w.units["NV-PS-SHN"].id, Case.id != hero.id,
        Document.sensitivity == "CONFIDENTIAL")).all()
    if shn_docs:
        d_ = shn_docs[0]
        w.request("NV-IO-1045", "SHARE", d_, "Needed by Rampur PS for a linked investigation",
                  {"grantee_user_id": w.users["NV-IO-2231"].id, "scope": "VIEW",
                   "expires_at": audit.iso(datetime(2026, 10, 10))})
    rmp_docs = db.scalars(select(Document).where(Document.case_id == rmp.id,
                                                 Document.doc_type == "SEIZURE_MEMO")).all()
    if rmp_docs:
        clock.tick(40)
        d_ = rmp_docs[0]
        lead = db.get(User, d_.custodian_id)
        db.add(CaseMember(case_id=rmp.id, user_id=w.users["NV-FSL-512"].id, capacity="FORENSIC",
                          added_by=lead.id))
        w.request(lead.service_id, "CUSTODY_TRANSFER", d_, "Exhibit sent for forensic examination",
                  {"from_user_id": lead.id, "to_user_id": w.users["NV-FSL-512"].id},
                  assigned_to="NV-FSL-512")

    # an active share to the prosecutor on a background case
    trial = next((c for c in cases if c.status == "UNDER_TRIAL"), None)
    if trial:
        d_ = db.scalars(select(Document).where(Document.case_id == trial.id)).first()
        clock.tick(30)
        r = w.request(db.get(User, trial.lead_io_id).service_id, "SHARE", d_,
                      "For trial preparation", {"grantee_user_id": w.users["NV-APP-077"].id,
                                                "scope": "VIEW_REDACTED" if d_.sensitivity == "VICTIM_PROTECTED" else "VIEW",
                                                "expires_at": audit.iso(datetime(2026, 10, 9))})
        sup = next(s for s, *_ in CAST if s.startswith("NV-SHO") and
                   w.users[s].unit_id == trial.unit_id)
        clock.tick(60)
        w.decide(sup, r)
        db.add(Share(document_id=d_.id, grantee_user_id=w.users["NV-APP-077"].id,
                     scope=r.payload["scope"], expires_at=datetime(2026, 10, 9), request_id=r.id,
                     created_by=r.requested_by, approved_by=w.users[sup].id))
        audit.record(db, w.ctx(sup), "SHARE_GRANTED",
                     f"Shared {d_.doc_number} with Farhan Siddiqui until 2026-10-09",
                     case_id=trial.id, document_id=d_.id, request_id=r.id,
                     target_user_id=w.users["NV-APP-077"].id)

    # nightly integrity sweep: genuinely re-verify everything older than a day
    clock.at(datetime(2026, 10, 1, 21, 30))
    versions = db.scalars(select(DocumentVersion).where(
        DocumentVersion.processing_status == "READY",
        DocumentVersion.uploaded_at < datetime(2026, 9, 26))).all()
    ok = 0
    for v in versions:
        r = integrity.verify_version(db, v)
        v.last_verified_at, v.last_verification = clock.t, r["overall"]
        ok += r["overall"] == "VERIFIED"
    audit.record(db, Ctx(), "INTEGRITY_VERIFIED",
                 f"Nightly integrity sweep: {ok}/{len(versions)} versions verified",
                 details={"verified": ok, "checked": len(versions)})
    result = audit.verify_chain(db)
    audit.record(db, Ctx(), "CHAIN_VERIFIED",
                 f"Nightly chain check: {result['status']} — {result['events_checked']} events",
                 details={"events_checked": result["events_checked"]})


def seed() -> None:
    """Fill an empty, migrated database. Runs as the app role (cfv_app) — it needs nothing more."""
    config.ensure_dirs()
    db = SessionLocal()
    clock = Clock(START - timedelta(minutes=1))
    clock.at(START)
    try:
        w = World(db, clock)
        _units_and_users(w)
        cases = _background(w)
        hero = _hero(w)
        _activity(w, hero, cases)
        db.commit()
    finally:
        models.clock_override = None
        db.close()


def reset_and_seed() -> None:
    """Rebuild the schema from the migrations (as owner), wipe stored files and keys, re-seed."""
    engine.dispose()
    migrate.reset()
    if config.DATA_DIR.exists():
        # Stored files are read-only (write-once); Windows refuses to delete those until the
        # read-only flag is cleared.
        def _clear_readonly(func, path, _exc):
            os.chmod(path, 0o644)
            func(path)
        # Empty the directory rather than removing it: in Docker it is a mounted volume.
        for child in config.DATA_DIR.iterdir():
            if child.is_dir():
                shutil.rmtree(child, onexc=_clear_readonly)
            else:
                _clear_readonly(os.unlink, child, None)
    config.ensure_dirs()
    crypto.reset_key_cache()
    security.reset_secret_cache()
    seed()


if __name__ == "__main__":
    import time
    t = time.perf_counter()
    reset_and_seed()
    with SessionLocal() as s:
        from sqlalchemy import func
        print(f"seeded in {time.perf_counter() - t:.1f}s:",
              s.scalar(select(func.count()).select_from(Case)), "cases,",
              s.scalar(select(func.count()).select_from(DocumentVersion)), "versions,",
              s.scalar(select(func.count()).select_from(models.AuditEvent)), "audit events,",
              s.scalar(select(func.count()).select_from(models.AuditCheckpoint)), "checkpoints")
