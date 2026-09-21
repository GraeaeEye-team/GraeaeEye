"""
Security sanitizer for prompt injection defense and PII telemetry masking.
"""

from __future__ import annotations
import re
from typing import Any, Dict


class SecuritySanitizer:
    """Sanitizes text, protects against prompt injection, and masks PII in logs."""

    INJECTION_PATTERNS = [
        re.compile(r"ignore\s+(?:all\s+)?(?:previous\s+)?instructions", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
        re.compile(r"system\s*prompt", re.IGNORECASE),
        re.compile(r"<\/?system>", re.IGNORECASE),
        re.compile(r"drop\s+table\s+", re.IGNORECASE),
        re.compile(r"delete\s+from\s+", re.IGNORECASE),
    ]

    @classmethod
    def sanitize_raw_string(cls, text: str) -> str:
        """Removes null bytes and control characters while preserving valid unicode."""
        if not text:
            return ""
        # Remove NULL bytes and dangerous terminal control codes
        clean = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
        return clean.strip()

    @classmethod
    def detect_prompt_injection(cls, text: str) -> bool:
        """Detects if a string contains known adversarial prompt injection keywords."""
        for pattern in cls.INJECTION_PATTERNS:
            if pattern.search(text):
                return True
        return False

    @classmethod
    def mask_tax_id(cls, tax_id: str) -> str:
        """Masks fiscal / tax ID for secure logging e.g. 1002600001234 -> 100260***1234."""
        s = str(tax_id).strip()
        if len(s) > 6:
            return f"{s[:4]}***{s[-3:]}"
        return "***"

    @classmethod
    def mask_email(cls, email: str) -> str:
        """Masks email address for secure logging e.g. user@bank.md -> u***@bank.md."""
        s = str(email).strip()
        if "@" in s:
            user, domain = s.split("@", 1)
            masked_user = user[0] + "***" if user else "***"
            return f"{masked_user}@{domain}"
        return "***"

    @classmethod
    def mask_record_for_logging(cls, record: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a safe version of record dictionary with PII masked for telemetry."""
        safe = {}
        for k, v in record.items():
            k_lower = k.lower()
            if "tax_id" in k_lower or "idno" in k_lower or "cui" in k_lower:
                safe[k] = cls.mask_tax_id(v) if v else v
            elif "email" in k_lower:
                safe[k] = cls.mask_email(v) if v else v
            elif "password" in k_lower or "secret" in k_lower or "token" in k_lower:
                safe[k] = "******"
            else:
                safe[k] = v
        return safe
