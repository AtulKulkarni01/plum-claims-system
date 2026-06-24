"""Generate realistic sample medical documents for testing Upload mode.

These are rendered (not scraped) so they are PII-free, reliable, and map to the
policy in policy_terms.json — while looking like real scanned Indian documents
(letterhead, itemized table, GSTIN, registration no, round stamp, signature).

    python -m scripts.make_samples      ->  writes ./samples/*.jpg
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
SAMPLES.mkdir(exist_ok=True)
W, H = 940, 760
INK = (30, 30, 38)
ACCENT = (38, 56, 120)
MUTED = (95, 100, 115)

_BOLD = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf"]
_REG = ["/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf"]


def font(size: int, bold: bool = False):
    for p in (_BOLD if bold else _REG):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _new():
    img = Image.new("RGB", (W, H), (252, 252, 250))
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, W - 10, H - 10], outline=(60, 60, 80), width=2)
    return img, d


def _header(d, name, sub):
    d.rectangle([10, 10, W - 10, 96], fill=ACCENT)
    d.text((34, 24), name, fill="white", font=font(28, True))
    d.text((34, 62), sub, fill=(214, 220, 240), font=font(15))


def _stamp(d, cx, cy, top, mid):
    d.ellipse([cx - 62, cy - 62, cx + 62, cy + 62], outline=(150, 40, 40), width=3)
    d.ellipse([cx - 50, cy - 50, cx + 50, cy + 50], outline=(150, 40, 40), width=1)
    for txt, dy, sz in ((top, -22, 13), (mid, -2, 16), ("VERIFIED", 20, 11)):
        w = d.textlength(txt, font=font(sz, True))
        d.text((cx - w / 2, cy + dy), txt, fill=(150, 40, 40), font=font(sz, True))


def _kv(d, x, y, rows, gap=30):
    for label, val in rows:
        d.text((x, y), label, fill=MUTED, font=font(15))
        d.text((x + 140, y), val, fill=INK, font=font(16, True))
        y += gap
    return y


def _table(d, x, y, w, headers, rows):
    cols = len(headers)
    colw = [w * 0.58] + [w * 0.42 / (cols - 1)] * (cols - 1) if cols > 1 else [w]
    d.rectangle([x, y, x + w, y + 30], fill=(235, 238, 246))
    cx = x
    for i, h in enumerate(headers):
        d.text((cx + 8, y + 7), h, fill=ACCENT, font=font(14, True))
        cx += colw[i]
    y += 30
    for r in rows:
        cx = x
        for i, c in enumerate(r):
            d.text((cx + 8, y + 7), str(c), fill=INK, font=font(15))
            cx += colw[i]
        d.line([x, y + 30, x + w, y + 30], fill=(220, 222, 230), width=1)
        y += 31
    return y


def save(img, name):
    img.save(SAMPLES / name, "JPEG", quality=92)
    print("wrote", name)


# 1) Prescription (EMP001 Rajesh Kumar) -> clean APPROVED
img, d = _new()
_header(d, "CITY MEDICAL CENTRE", "12 MG Road, Bengaluru 560001  |  Ph: 080-4123-7788")
d.text((34, 116), "Dr. Arun Sharma, MBBS, MD (Internal Medicine)", fill=INK, font=font(18, True))
d.text((34, 142), "Reg. No: KA/45678/2015", fill=MUTED, font=font(15))
d.line([34, 174, W - 34, 174], fill=(210, 212, 220), width=1)
y = _kv(d, 34, 190, [("Patient", "Rajesh Kumar"), ("Age / Sex", "39 / M"),
                     ("Date", "01-Nov-2024"), ("Diagnosis", "Viral Fever")])
d.text((34, y + 8), "Rx", fill=ACCENT, font=font(18, True))
for i, line in enumerate(["1.  Tab Paracetamol 650mg    1-1-1  x 5 days",
                          "2.  Tab Vitamin C 500mg      0-0-1  x 7 days"]):
    d.text((50, y + 40 + i * 30), line, fill=INK, font=font(16))
d.text((34, y + 116), "Investigations: CBC, Dengue NS1", fill=INK, font=font(15))
d.text((34, H - 70), "Signature: ____________________", fill=MUTED, font=font(15))
_stamp(d, W - 110, H - 110, "KA MEDICAL", "Dr. A. SHARMA")
save(img, "sample_prescription.jpg")

# 2) Hospital bill (EMP001) -> clean APPROVED (₹1,350 after 10% co-pay)
img, d = _new()
_header(d, "CITY MEDICAL CENTRE", "GSTIN: 29ABCDE1234F1ZX  |  12 MG Road, Bengaluru")
d.text((34, 116), "BILL / RECEIPT", fill=ACCENT, font=font(20, True))
_kv(d, 34, 150, [("Bill No", "CMC/2024/08321"), ("Date", "01-Nov-2024"),
                 ("Patient", "Rajesh Kumar")], gap=28)
y = _table(d, 34, 250, W - 68, ["Description", "Amount (Rs.)"],
           [("Consultation Fee (OPD)", "1000.00"),
            ("CBC (Complete Blood Count)", "300.00"),
            ("Dengue NS1 Antigen Test", "200.00")])
d.text((W - 320, y + 16), "Total Amount:", fill=INK, font=font(17, True))
d.text((W - 150, y + 16), "Rs. 1500.00", fill=INK, font=font(17, True))
d.text((34, H - 70), "Payment: UPI / Card", fill=MUTED, font=font(15))
_stamp(d, W - 110, H - 110, "CITY MEDICAL", "PAID")
save(img, "sample_hospital_bill.jpg")

# 3) Dental bill (EMP002 Priya Singh) -> PARTIAL (whitening excluded)
img, d = _new()
_header(d, "SMILE DENTAL CLINIC", "GSTIN: 29SMILE5678D1ZP  |  Indiranagar, Bengaluru")
d.text((34, 116), "TAX INVOICE", fill=ACCENT, font=font(20, True))
_kv(d, 34, 150, [("Bill No", "SDC/2024/1187"), ("Date", "15-Oct-2024"),
                 ("Patient", "Priya Singh")], gap=28)
y = _table(d, 34, 250, W - 68, ["Procedure", "Amount (Rs.)"],
           [("Root Canal Treatment", "8000.00"),
            ("Teeth Whitening", "4000.00")])
d.text((W - 320, y + 16), "Total Amount:", fill=INK, font=font(17, True))
d.text((W - 160, y + 16), "Rs. 12000.00", fill=INK, font=font(17, True))
_stamp(d, W - 110, H - 110, "SMILE DENTAL", "PAID")
save(img, "sample_dental_bill.jpg")

# 4a) Excluded-condition prescription (EMP009 Anita Desai) -> REJECTED
img, d = _new()
_header(d, "WELLNESS WEIGHT CLINIC", "Salt Lake, Kolkata 700091")
d.text((34, 116), "Dr. P. Banerjee, MBBS, MS", fill=INK, font=font(18, True))
d.text((34, 142), "Reg. No: WB/34567/2015", fill=MUTED, font=font(15))
d.line([34, 174, W - 34, 174], fill=(210, 212, 220), width=1)
_kv(d, 34, 190, [("Patient", "Anita Desai"), ("Age / Sex", "31 / F"),
                 ("Date", "18-Oct-2024"), ("Diagnosis", "Morbid Obesity - BMI 37"),
                 ("Treatment", "Bariatric Consultation + Customised Diet Plan")])
d.text((34, H - 70), "Signature: ____________________", fill=MUTED, font=font(15))
_stamp(d, W - 110, H - 110, "WB MEDICAL", "Dr. BANERJEE")
save(img, "sample_obesity_prescription.jpg")

# 4b) Excluded-condition bill
img, d = _new()
_header(d, "WELLNESS WEIGHT CLINIC", "GSTIN: 19WELL9012K1ZW  |  Salt Lake, Kolkata")
d.text((34, 116), "BILL / RECEIPT", fill=ACCENT, font=font(20, True))
_kv(d, 34, 150, [("Bill No", "WC/2024/4421"), ("Date", "18-Oct-2024"),
                 ("Patient", "Anita Desai")], gap=28)
y = _table(d, 34, 250, W - 68, ["Service", "Amount (Rs.)"],
           [("Bariatric Consultation", "3000.00"),
            ("Personalised Diet & Nutrition Program", "5000.00")])
d.text((W - 320, y + 16), "Total Amount:", fill=INK, font=font(17, True))
d.text((W - 150, y + 16), "Rs. 8000.00", fill=INK, font=font(17, True))
_stamp(d, W - 110, H - 110, "WELLNESS", "PAID")
save(img, "sample_obesity_bill.jpg")

# 5) Wrong-patient bill -> PATIENT_MISMATCH with the prescription
img, d = _new()
_header(d, "CITY MEDICAL CENTRE", "GSTIN: 29ABCDE1234F1ZX  |  12 MG Road, Bengaluru")
d.text((34, 116), "BILL / RECEIPT", fill=ACCENT, font=font(20, True))
_kv(d, 34, 150, [("Bill No", "CMC/2024/08399"), ("Date", "01-Nov-2024"),
                 ("Patient", "Arjun Mehta")], gap=28)
y = _table(d, 34, 250, W - 68, ["Description", "Amount (Rs.)"],
           [("Consultation Fee (OPD)", "1000.00"),
            ("CBC (Complete Blood Count)", "300.00")])
d.text((W - 320, y + 16), "Total Amount:", fill=INK, font=font(17, True))
d.text((W - 150, y + 16), "Rs. 1300.00", fill=INK, font=font(17, True))
_stamp(d, W - 110, H - 110, "CITY MEDICAL", "PAID")
save(img, "sample_bill_wrong_patient.jpg")

print("done ->", SAMPLES)
