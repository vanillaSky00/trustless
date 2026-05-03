"""Regex-based pattern detection for fast initial risk screening.

This is the cheap pre-filter before the LLM validator runs. It catches the
80% of obvious attacks (multi-pattern matches) so the agent can short-circuit
without an LLM call when the verdict is unambiguous.

Patterns are inherited from the Task 2 ZT PEP filter and grouped by category.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PatternMatchResult:
    """Output of pattern scanning."""

    score: float
    signals: list[str]


# ---------------------------------------------------------------------------
# Pattern catalogue
# Each list represents one category. Hits across multiple categories
# compound the score because real attacks tend to chain techniques.
# ---------------------------------------------------------------------------

INJECTION_PATTERNS: list[str] = [
    r"ignore\s+(your\s+)?(previous|all|prior|above)\s+instructions?",
    r"disregard\s+(your\s+)?(previous|system|all)\s+",
    r"forget\s+(everything|all|your)\s+",
    r"you\s+are\s+now\s+(a|an|the)\s+",
    r"new\s+persona",
    r"act\s+as\s+if\s+you\s+(have\s+no|don.t\s+have)",
    r"pretend\s+(you\s+are|to\s+be)\s+",
    r"reveal\s+(your\s+)?(system\s+prompt|instructions|training)",
    r"repeat\s+(everything|the\s+above|your\s+prompt)",
    r"print\s+(your\s+)?(system|initial)\s+(prompt|instructions)",
    r"what\s+(were\s+)?your\s+(exact\s+)?instructions",
    r"<!--.*-->",
    r"\[SYSTEM\]",
    r"<\|.*\|>",
]

ESCALATION_PATTERNS: list[str] = [
    r"\b(sudo|root|admin|superuser)\b",
    r"grant\s+(me\s+)?(admin|root|full|all)\s+(access|permissions?|privileges?)",
    r"override\s+(security|policy|restriction|filter|rule)",
    r"bypass\s+(authentication|auth|2fa|mfa|security|filter)",
    r"disable\s+(security|filter|restriction|protection)",
    r"i\s+(am|have)\s+(admin|root|superuser|cto|ciso)\s+(access|privileges?|rights?)?",
    r"as\s+an?\s+(administrator|admin|root|superuser)",
    r"unrestricted\s+(access|mode)",
]

EXFILTRATION_PATTERNS: list[str] = [
    r"export\s+(all|entire|full|every|the\s+whole)\s+",
    r"dump\s+(the\s+)?(database|db|all\s+data|everything)",
    r"(show|list|print|give)\s+me\s+(all\s+)?(users?|passwords?|credentials?|keys?|tokens?|secrets?)",
    r"(extract|exfiltrate|steal|copy)\s+(all|every|the\s+entire)\s+",
    r"(api|access|secret|private)\s+keys?",
    r"connection\s+string",
    r"(database|db)\s+(credentials?|password|username)",
    r"(ssh|private)\s+key",
    r"\.env\s+file",
    r"/etc/(passwd|shadow|sudoers)",
]

# Score weights tuned so that a single category match → step-up territory,
# multi-category match → deny territory.
_CATEGORY_WEIGHTS = {
    "injection": (0.50, 0.05),       # (base, per-additional-hit)
    "privilege_escalation": (0.40, 0.05),
    "exfiltration": (0.45, 0.05),
}


def _match(text: str, patterns: list[str]) -> int:
    """Return number of distinct patterns from the list that matched."""
    text_lower = text.lower()
    return sum(1 for p in patterns if re.search(p, text_lower))


def scan(prompt: str) -> PatternMatchResult:
    """Score a prompt against all pattern categories.

    Returns a result with score in [0, 1] and a list of signal labels
    that triggered. Signal labels are human-readable for logging.
    """
    score = 0.0
    signals: list[str] = []

    categories = [
        ("injection", INJECTION_PATTERNS),
        ("privilege_escalation", ESCALATION_PATTERNS),
        ("exfiltration", EXFILTRATION_PATTERNS),
    ]

    for name, patterns in categories:
        hits = _match(prompt, patterns)
        if hits:
            base, per_hit = _CATEGORY_WEIGHTS[name]
            score += base + (hits - 1) * per_hit
            signals.append(f"{name}({hits})")

    return PatternMatchResult(score=min(score, 1.0), signals=signals)
