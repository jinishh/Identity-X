"""BSA 2023 §63 certificate, pre-filled for signature (docs/03-integrity-model.md §6).

The system fills what it can attest (Part A particulars, hash values). Signatures of the person
in charge and of the expert (Part B) are left blank — the PDF never claims admissibility.
"""

import io

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .models import Certificate

NAVY = colors.HexColor("#1e2a4a")
MUTED = colors.HexColor("#5b6478")


def _wrap(c: canvas.Canvas, text: str, x: float, y: float, width: float, size=9, leading=12,
          font="Helvetica") -> float:
    c.setFont(font, size)
    words, line = text.split(), ""
    for w in words:
        trial = f"{line} {w}".strip()
        if c.stringWidth(trial, font, size) > width:
            c.drawString(x, y, line)
            y -= leading
            line = w
        else:
            line = trial
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


def render(cert: Certificate, verify_url: str, sig_fingerprint: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    L, R = 18 * mm, W - 18 * mm
    a, b = cert.part_a, cert.part_b

    c.setFillColor(NAVY)
    c.rect(0, H - 30 * mm, W, 30 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(L, H - 14 * mm, "CERTIFICATE UNDER SECTION 63(4)")
    c.setFont("Helvetica", 10)
    c.drawString(L, H - 20 * mm, "Bharatiya Sakshya Adhiniyam, 2023 — electronic record")
    c.drawRightString(R, H - 14 * mm, cert.cert_number)
    c.setFont("Helvetica", 8)
    c.drawRightString(R, H - 20 * mm, "Pre-filled by Case-File Vault · requires signatures below")

    y = H - 40 * mm
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(L, y, "PART A — particulars of the electronic record (filled by the system)")
    y -= 8 * mm
    rows = [
        ("Case number", a["case_number"]), ("FIR", a["fir"]), ("Document", a["document"]),
        ("Document number / version", f'{a["doc_number"]} · v{a["version_no"]}'),
        ("File name", a["file_name"]), ("Type / size", f'{a["mime"]} · {a["size_bytes"]:,} bytes'),
        ("Received into system", a["received_at"]), ("Uploaded by", a["uploaded_by"]),
        ("Computer resource", a["system"]),
        ("Integrity controls", a["controls"]),
        ("Chain of custody", a["custody_summary"]),
    ]
    for label, value in rows:
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8.5)
        c.drawString(L, y, label)
        c.setFillColor(colors.black)
        y = _wrap(c, str(value), L + 48 * mm, y, R - L - 48 * mm, size=9)
        y -= 2

    y -= 4 * mm
    c.setFillColor(colors.HexColor("#f2f4f8"))
    c.roundRect(L, y - 20 * mm, R - L, 22 * mm, 3 * mm, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(L + 4 * mm, y - 5 * mm, "Hash value (SHA-256) of the electronic record")
    c.setFont("Courier-Bold", 9.5)
    c.drawString(L + 4 * mm, y - 11 * mm, cert.sha256[:32])
    c.drawString(L + 4 * mm, y - 16 * mm, cert.sha256[32:])
    y -= 28 * mm

    c.setFillColor(colors.black)
    y = _wrap(c, "I certify that the particulars above are true to the best of my knowledge and "
                 "that the electronic record was produced from the computer resource described, "
                 "which was operating properly during the period of its storage.", L, y, R - L)
    y -= 10 * mm
    c.setFont("Helvetica", 9)
    c.line(L, y, L + 70 * mm, y)
    c.drawString(L, y - 4 * mm, f"{cert.signatory_name}, {cert.signatory_designation}")
    c.drawString(L, y - 8 * mm, "Person in charge of the computer resource — signature, date, place")
    y -= 20 * mm

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(L, y, "PART B — expert (to be completed by the expert)")
    y -= 7 * mm
    c.setFillColor(colors.black)
    y = _wrap(c, f"Algorithm: {b['algorithm']}. Hash value to be independently confirmed by the "
                 f"expert: {cert.sha256[:16]}… (full value above).", L, y, R - L)
    y -= 10 * mm
    c.line(L, y, L + 70 * mm, y)
    c.drawString(L, y - 4 * mm, "Name, designation, signature of the expert")

    qr = qrcode.make(verify_url, box_size=4, border=1)
    qbuf = io.BytesIO()
    qr.save(qbuf, format="PNG")
    c.drawImage(ImageReader(io.BytesIO(qbuf.getvalue())), R - 32 * mm, 16 * mm, 30 * mm, 30 * mm)
    c.setFont("Helvetica", 7.5)
    c.setFillColor(MUTED)
    c.drawString(L, 30 * mm, f"Verify: {verify_url}")
    c.drawString(L, 26 * mm, f"Verification code: {cert.verification_code}")
    c.drawString(L, 22 * mm, f"System signature (Ed25519, {cert.signing_key_id}): {sig_fingerprint}")
    c.drawString(L, 18 * mm, "A matching hash shows the bytes are unchanged. It does not by itself "
                             "establish authorship or admissibility.")
    c.showPage()
    c.save()
    return buf.getvalue()
