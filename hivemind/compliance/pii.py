"""
PIIRedactor: scan and redact PII from text before storage.
Detectors: regex (EMAIL, PHONE, SSN, CREDIT_CARD, IP, API_KEY) + optional spaCy NER (NAME, ADDRESS).
"""

import re
from dataclasses import dataclass, field


@dataclass
class PIIDetection:
    pii_type: str
    start: int
    end: int
    confidence: float


@dataclass
class RedactionResult:
    redacted_text: str
    detections: list[PIIDetection] = field(default_factory=list)
    pii_found: bool = False


# Regex patterns (non-capturing for substitution)
PATTERNS = {
    "EMAIL": re.compile(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        re.IGNORECASE,
    ),
    "PHONE": re.compile(
        r"\+?[\d\s\-()]{10,20}\d",
    ),
    "SSN": re.compile(
        r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b",
    ),
    "CREDIT_CARD": re.compile(
        r"\b(?:\d[-\s]*){13,19}\d\b",
    ),
    "IP_ADDRESS": re.compile(
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\[?[0-9a-fA-F:.]+\]?",
    ),
    "API_KEY": re.compile(
        r"\b(?:sk|pk)[-_][a-zA-Z0-9]{20,}\b",
    ),
}


def _luhn_ok(digits: str) -> bool:
    s = digits.replace(" ", "").replace("-", "")
    if len(s) < 13:
        return False
    try:
        nums = [int(c) for c in s]
    except ValueError:
        return False
    total = 0
    for i, d in enumerate(reversed(nums)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class PIIRedactor:
    """Redact PII from text. Configurable pii_types; optional spaCy for NAME/ADDRESS when gdpr_mode."""

    def __init__(
        self,
        pii_types: list[str] | None = None,
        gdpr_mode: bool = False,
    ) -> None:
        self.pii_types = pii_types or list(PATTERNS.keys())
        self.gdpr_mode = gdpr_mode
        self._ner_available: bool | None = None

    def _ner_detect(self, text: str) -> list[PIIDetection]:
        out: list[PIIDetection] = []
        if self._ner_available is False:
            return out
        try:
            import spacy
            if self._ner_available is None:
                try:
                    nlp = spacy.load("en_core_web_sm")
                except Exception:
                    nlp = spacy.blank("en")
                setattr(self, "_ner", nlp)
                self._ner_available = True
        except ImportError:
            self._ner_available = False
            return out
        nlp = getattr(self, "_ner", None)
        if nlp is None:
            return out
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ in ("PERSON", "GPE", "LOC") and (self.gdpr_mode or ent.label_ == "PERSON"):
                out.append(PIIDetection(
                    pii_type="NAME" if ent.label_ == "PERSON" else "ADDRESS",
                    start=ent.start_char,
                    end=ent.end_char,
                    confidence=0.9,
                ))
        return out

    def redact(self, text: str) -> RedactionResult:
        if not text:
            return RedactionResult(redacted_text="", detections=[], pii_found=False)
        detections: list[PIIDetection] = []
        ner_done = False
        for pii_type in self.pii_types:
            if pii_type not in PATTERNS and pii_type not in ("NAME", "ADDRESS"):
                continue
            if pii_type in ("NAME", "ADDRESS") or self.gdpr_mode:
                if not ner_done:
                    detections.extend(self._ner_detect(text))
                    ner_done = True
                continue
            pattern = PATTERNS[pii_type]
            for m in pattern.finditer(text):
                snippet = m.group(0)
                if pii_type == "CREDIT_CARD" and not _luhn_ok(snippet):
                    continue
                detections.append(PIIDetection(
                    pii_type=pii_type,
                    start=m.start(),
                    end=m.end(),
                    confidence=0.95,
                ))
        detections.sort(key=lambda d: (d.start, -d.end))
        merged: list[PIIDetection] = []
        for d in detections:
            if merged and d.start < merged[-1].end:
                continue
            merged.append(d)
        result = list(text)
        for d in reversed(merged):
            result[d.start:d.end] = f"[REDACTED:{d.pii_type}]"
        redacted_text = "".join(result)
        return RedactionResult(
            redacted_text=redacted_text,
            detections=merged,
            pii_found=len(merged) > 0,
        )
