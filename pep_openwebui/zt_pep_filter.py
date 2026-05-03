"""
title: Zero Trust PEP Stateful Risk Filter
author: vanillasky
version: 1.0.0
license: MIT
description: Stateful Policy Enforcement Point for Zero Trust Architecture. Classifies prompts for injection, privilege escalation, and exfiltration patterns. Uses short-term session memory (STM) to detect slow-burn multi-turn attacks. Implements allow / step-up / deny enforcement tiers.
"""

from pydantic import BaseModel, Field
from typing import Optional
import re
import time
import json


class Filter:
    class Valves(BaseModel):
        deny_threshold: float = Field(
            default=0.75,
            description="Risk score at or above this value triggers a DENY decision",
        )
        stepup_threshold: float = Field(
            default=0.45,
            description="Risk score at or above this value (but below deny) triggers STEP-UP",
        )
        session_window: int = Field(
            default=8,
            description="Number of recent turns to retain in short-term memory per user",
        )
        session_escalation_weight: float = Field(
            default=0.15,
            description="Additional risk added per suspicious turn already in STM window",
        )
        enable_injection_detection: bool = Field(
            default=True,
            description="Detect known prompt injection patterns in user messages",
        )
        enable_escalation_detection: bool = Field(
            default=True,
            description="Detect privilege escalation language (admin, override, ignore instructions)",
        )
        enable_exfiltration_detection: bool = Field(
            default=True,
            description="Detect data exfiltration signals (export all, dump, credentials)",
        )
        show_risk_score: bool = Field(
            default=True,
            description="Show the computed risk score in the enforcement message",
        )
        show_triggered_rules: bool = Field(
            default=True,
            description="Show which detection rules fired in the enforcement message",
        )

    def __init__(self):
        self.name = "Zero Trust PEP Stateful Risk Filter"
        self.valves = self.Valves()

        # Short-Term Memory: user_id -> list of turn dicts
        self._stm = {}

        # --- Detection rule sets ---
        self._injection_patterns = [
            r"ignore\s+(previous|all|prior|above)\s+instructions?",
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

        self._escalation_patterns = [
            r"\b(sudo|root|admin|superuser)\b",
            r"grant\s+(me\s+)?(admin|root|full|all)\s+(access|permissions?|privileges?)",
            r"override\s+(security|policy|restriction|filter|rule)",
            r"bypass\s+(authentication|auth|2fa|mfa|security|filter)",
            r"disable\s+(security|filter|restriction|protection)",
            r"i\s+(am|have)\s+(admin|root|superuser|cto|ciso)\s+(access|privileges?|rights?)?",
            r"as\s+an?\s+(administrator|admin|root|superuser)",
            r"unrestricted\s+(access|mode)",
        ]

        self._exfiltration_patterns = [
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

    # ------------------------------------------------------------------
    # Detection helpers
    # ------------------------------------------------------------------

    def _match_patterns(self, text, patterns):
        text_lower = text.lower()
        matched = []
        for pattern in patterns:
            if re.search(pattern, text_lower):
                matched.append(pattern)
        return matched

    def _compute_base_risk(self, prompt):
        score = 0.0
        triggered = []

        if self.valves.enable_injection_detection:
            hits = self._match_patterns(prompt, self._injection_patterns)
            if hits:
                score += 0.50 + (len(hits) - 1) * 0.05
                triggered.append("injection({} patterns)".format(len(hits)))

        if self.valves.enable_escalation_detection:
            hits = self._match_patterns(prompt, self._escalation_patterns)
            if hits:
                score += 0.40 + (len(hits) - 1) * 0.05
                triggered.append("privilege_escalation({} patterns)".format(len(hits)))

        if self.valves.enable_exfiltration_detection:
            hits = self._match_patterns(prompt, self._exfiltration_patterns)
            if hits:
                score += 0.45 + (len(hits) - 1) * 0.05
                triggered.append("exfiltration({} patterns)".format(len(hits)))

        return min(score, 1.0), triggered

    def _get_session_risk_modifier(self, user_id):
        history = self._stm.get(user_id, [])
        suspicious_turns = [
            t for t in history
            if t.get("risk", 0.0) > 0.2 or t.get("decision") in ("step_up", "deny")
        ]
        modifier = len(suspicious_turns) * self.valves.session_escalation_weight
        return min(modifier, 0.40)

    def _make_decision(self, score):
        if score >= self.valves.deny_threshold:
            return "deny"
        elif score >= self.valves.stepup_threshold:
            return "step_up"
        return "allow"

    def _update_stm(self, user_id, turn):
        window = self._stm.setdefault(user_id, [])
        window.append(turn)
        self._stm[user_id] = window[-self.valves.session_window:]

    def _format_decision_message(self, decision, score, triggered, session_modifier):
        score_str = " (risk score: {:.2f})".format(score) if self.valves.show_risk_score else ""
        rules_str = ""
        if self.valves.show_triggered_rules and triggered:
            rules_str = "\nTriggered rules: {}".format(", ".join(triggered))
            if session_modifier > 0:
                rules_str += "\nSession escalation modifier: +{:.2f}".format(session_modifier)

        if decision == "deny":
            return (
                "🛑 **Zero Trust PEP — Access Denied**{}\n"
                "This request has been blocked by the stateful risk filter.{}\n\n"
                "If you believe this is a mistake, please contact your administrator."
            ).format(score_str, rules_str)

        elif decision == "step_up":
            return (
                "🔐 **Zero Trust PEP — Additional Verification Required**{}\n"
                "This request requires confirmation before proceeding.{}\n\n"
                "Please confirm your intent or provide additional context."
            ).format(score_str, rules_str)

        return ""

    # ------------------------------------------------------------------
    # Open WebUI Filter hooks
    # ------------------------------------------------------------------

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        user_id = (user or {}).get("id", "anonymous")
        messages = body.get("messages", [])

        user_messages = [m for m in messages if m.get("role") == "user"]
        if not user_messages:
            return body

        prompt = user_messages[-1].get("content", "")

        # Stage 1: INSPECT
        base_risk, triggered = self._compute_base_risk(prompt)

        # Stage 2: ASSESS (STM)
        session_modifier = self._get_session_risk_modifier(user_id)
        total_risk = min(base_risk + session_modifier, 1.0)

        # Stage 3: ENFORCE
        decision = self._make_decision(total_risk)

        # Write to STM
        self._update_stm(user_id, {
            "prompt": prompt[:200],
            "risk": total_risk,
            "decision": decision,
            "triggered": triggered,
            "ts": time.time(),
        })

        # Attach metadata for outlet()
        body["__zt_pep__"] = {
            "decision": decision,
            "risk_score": total_risk,
            "base_risk": base_risk,
            "session_modifier": session_modifier,
            "triggered": triggered,
            "user_id": user_id,
        }

        # Enforce: inject refusal for non-allow decisions
        if decision in ("deny", "step_up"):
            enforcement_msg = self._format_decision_message(
                decision, total_risk, triggered, session_modifier
            )
            body["messages"].append({
                "role": "assistant",
                "content": enforcement_msg,
            })

        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        pep_meta = body.get("__zt_pep__", {})
        if pep_meta:
            audit = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "user_id": pep_meta.get("user_id"),
                "decision": pep_meta.get("decision"),
                "risk_score": round(pep_meta.get("risk_score", 0.0), 3),
                "triggered_rules": pep_meta.get("triggered", []),
            }
            print("[ZT-PEP AUDIT] {}".format(json.dumps(audit)))

        return body
