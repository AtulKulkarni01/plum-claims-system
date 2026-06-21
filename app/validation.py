"""Deterministic document-data validation and normalization.

Pure functions used by the extraction stage: validate Indian doctor registration
numbers against the state formats in sample_documents_guide.md, and expand common
medical shorthand into full diagnosis terms. No I/O, no LLM.
"""

from __future__ import annotations

import re
from typing import Optional

# State medical-council registration formats (sample_documents_guide.md):
# shared shape <STATE>/<5-6 digits>/<4-digit year>; Ayurveda is national.
_STATE_CODES = ["KA", "MH", "DL", "TN", "GJ", "AP", "UP", "WB", "KL"]
_REGISTRATION_PATTERNS = [
    re.compile(rf"^(?:{'|'.join(_STATE_CODES)})/\d{{4,6}}/\d{{4}}$", re.I),
    re.compile(r"^AYUR/[A-Z]{2}/\d{3,6}/\d{4}$", re.I),  # AYUR/KL/2345/2019
]


def validate_registration(registration: Optional[str]) -> bool:
    """True if the registration number matches a recognized Indian format."""
    if not registration:
        return False
    return any(p.match(registration.strip()) for p in _REGISTRATION_PATTERNS)


# Common Indian medical shorthand -> full term (sample_documents_guide.md).
_SHORTHAND = {
    "htn": "Hypertension",
    "t2dm": "Type 2 Diabetes Mellitus",
    "t1dm": "Type 1 Diabetes Mellitus",
    "uri": "Upper Respiratory Infection",
    "uti": "Urinary Tract Infection",
    "gerd": "Gastroesophageal Reflux Disease",
    "copd": "Chronic Obstructive Pulmonary Disease",
    "ibs": "Irritable Bowel Syndrome",
}
_SHORTHAND_RE = re.compile(r"\b(" + "|".join(_SHORTHAND) + r")\b", re.I)


def expand_shorthand(diagnosis: Optional[str]) -> Optional[str]:
    """Expand whole-word medical abbreviations; leave everything else untouched."""
    if not diagnosis:
        return diagnosis
    return _SHORTHAND_RE.sub(lambda m: _SHORTHAND[m.group(0).lower()], diagnosis)
