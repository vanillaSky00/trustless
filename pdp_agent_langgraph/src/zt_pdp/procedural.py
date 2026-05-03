"""Procedural memory — hard rules the agent cannot override.

These are deterministic constraints that fire regardless of what the LLM
or the pattern matcher say. In Zero Trust terms, this is the procedural
layer of the policy (NIST SP 800-207): non-negotiable rules encoded once
and enforced consistently.

Rules are intentionally simple and auditable. Add new ones here, not in
the LLM prompt — that way they are reviewable and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from zt_pdp.schemas import AccessRequest


@dataclass(frozen=True)
class ProceduralRule:
    """A single hard rule.

    `name`     — short identifier shown in logs and decisions
    `predicate` — function that returns True if the rule applies and forces deny
    `reason`    — human-readable explanation for audit trail
    """

    name: str
    predicate: Callable[[AccessRequest], bool]
    reason: str


# ---------------------------------------------------------------------------
# The rule set
# ---------------------------------------------------------------------------

def _intern_accessing_prod(req: AccessRequest) -> bool:
    """Interns may not access production resources, ever."""
    if req.user_role != "intern":
        return False
    text = req.prompt.lower()
    return any(token in text for token in ["prod ", "production", "prod db", "prod database"])


def _anonymous_credential_access(req: AccessRequest) -> bool:
    """Anonymous/unauthenticated users may not request credentials."""
    if req.user_id and req.user_id != "anonymous":
        return False
    text = req.prompt.lower()
    return any(
        token in text
        for token in ["password", "credential", "api key", "secret", "private key"]
    )


def _self_asserted_root_with_destructive_action(req: AccessRequest) -> bool:
    """Reject self-asserted root authority paired with destructive verbs.

    This is the memory-poisoning defence — even if Adaptive Memory stored
    a 'user is CTO' fact, the procedural layer blocks dangerous actions
    that assert authority within the request itself.
    """
    text = req.prompt.lower()
    asserts_authority = any(
        phrase in text
        for phrase in [
            "i am the cto",
            "i am admin",
            "i am the admin",
            "i am root",
            "as admin",
            "as the cto",
            "as an administrator",
        ]
    )
    destructive = any(
        verb in text
        for verb in ["delete all", "drop database", "rm -rf", "wipe", "destroy"]
    )
    return asserts_authority and destructive


RULES: list[ProceduralRule] = [
    ProceduralRule(
        name="intern_no_prod",
        predicate=_intern_accessing_prod,
        reason="Procedural rule: interns are not authorized to access production systems.",
    ),
    ProceduralRule(
        name="no_anon_credentials",
        predicate=_anonymous_credential_access,
        reason="Procedural rule: anonymous users cannot request credentials, secrets, or keys.",
    ),
    ProceduralRule(
        name="no_self_asserted_destruction",
        predicate=_self_asserted_root_with_destructive_action,
        reason="Procedural rule: destructive actions paired with self-asserted authority are denied; verifiable identity required.",
    ),
]


def check(req: AccessRequest) -> ProceduralRule | None:
    """Return the first rule that fires, or None if all pass.

    Order matters slightly — more specific rules go first so the audit
    log identifies the most precise reason for denial.
    """
    for rule in RULES:
        if rule.predicate(req):
            return rule
    return None
