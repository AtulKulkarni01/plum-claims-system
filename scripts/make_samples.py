"""Generate clean, realistic sample document images for testing Upload mode.

Generated (not scraped) so the demo is reliable and the content is known. Run:
    python -m scripts.make_samples
Outputs into ./samples/.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
SAMPLES.mkdir(exist_ok=True)


def _font(size: int) -> ImageFont.ImageFont:
    for path in ("/System/Library/Fonts/Supplemental/Arial.ttf",
                 "/Library/Fonts/Arial.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(name: str, title: str, lines: list[str], size=(820, 600)) -> None:
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    d.text((30, 24), title, fill="black", font=_font(28))
    d.line((30, 70, size[0] - 30, 70), fill="black", width=2)
    y = 92
    for ln in lines:
        d.text((30, y), ln, fill="black", font=_font(23))
        y += 38
    img.save(SAMPLES / name, "JPEG", quality=90)
    print("wrote", SAMPLES / name)


render("sample_prescription.jpg",
       "Dr. Arun Sharma, MBBS, MD (Internal Medicine)",
       ["Reg. No: KA/45678/2015",
        "City Medical Centre, 12 MG Road, Bengaluru",
        "",
        "Patient: Rajesh Kumar        Date: 01-Nov-2024",
        "Age: 39    Gender: M",
        "Diagnosis: Viral Fever",
        "",
        "Rx:",
        "1. Tab Paracetamol 650mg   1-1-1 x 5 days",
        "2. Tab Vitamin C 500mg     0-0-1 x 7 days",
        "Investigations: CBC, Dengue NS1"])

render("sample_hospital_bill.jpg",
       "CITY MEDICAL CENTRE  -  Bill / Receipt",
       ["Bill No: CMC/2024/08321      Date: 01-Nov-2024",
        "Patient: Rajesh Kumar",
        "",
        "Consultation Fee (OPD) .............. 1000.00",
        "CBC (Complete Blood Count) ......... 300.00",
        "Dengue NS1 Antigen Test ............ 200.00",
        "",
        "Total Amount: 1500.00"])

render("sample_dental_bill.jpg",
       "SMILE DENTAL CLINIC  -  Invoice",
       ["Bill No: SDC/2024/1187      Date: 15-Oct-2024",
        "Patient: Priya Singh",
        "",
        "Root Canal Treatment ............... 8000.00",
        "Teeth Whitening .................... 4000.00",
        "",
        "Total Amount: 12000.00"])
