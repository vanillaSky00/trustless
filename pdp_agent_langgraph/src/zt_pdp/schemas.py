"""Pydantic schemas for the agent's state, requests, and decisions.

These are the contracts between every node in the LangGraph state machine.
Keeping them in one file makes the data flow easy to audit.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

class AccessRequest(BaseModel):
    """A request that the PDP must decide on.

    This is the agent's primary input — what the PEP would forward upstream
    in a real Zero Trust deployment.
    """

    user_id: str = Field(description="Stable identifier for the requesting subject")
    prompt: str = Field(description="The user's actual message / requested action")
    user_role: str | None = Field(default=None, description="Asserted role (untrusted)")
    behavioral_cluster: str | None = Field(
        default=None,
        description="DBSCAN cluster ID or 'noise' from the behavioral PIP. None if unavailable.",
    )


# ---------------------------------------------------------------------------
# Decision contract
# ---------------------------------------------------------------------------

DecisionLiteral = Literal["allow", "step_up", "deny"]


class PDPDecision(BaseModel):
    """The structured output of the PDP agent.

    This is what the PEP receives back. It must always be returned —
    every code path through the graph populates this.
    """

    decision: DecisionLiteral = Field(description="The enforcement action to take")
    trust_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Computed trust score (1.0 = fully trusted, 0.0 = no trust)",
    )
    risk_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Inverse of trust — risk this request poses if allowed",
    )
    reason: str = Field(description="Human-readable explanation of the decision")
    triggered_signals: list[str] = Field(
        default_factory=list,
        description="Specific risk signals that influenced the decision",
    )
    used_memory: bool = Field(
        default=False,
        description="Whether the decision drew on retrieved long-term memories",
    )
    procedural_override: bool = Field(
        default=False,
        description="True if a hard procedural rule forced the decision regardless of LLM output",
    )


class LLMValidatorOutput(BaseModel):
    """Schema the LLM PEP validator must return.

    The LLM reasons over the request + retrieved memory + pattern signals
    and produces a structured judgement that the agent uses to compose the
    final PDPDecision. Separated from PDPDecision so the LLM has a smaller,
    less ambiguous schema to fill.
    """

    risk_assessment: Literal["low", "medium", "high"] = Field(
        description="Categorical risk judgement"
    )
    risk_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Numeric risk score the LLM judges based on context",
    )
    reasoning: str = Field(
        description="Brief justification — what about the request was risky or safe"
    )
    suspected_attack_type: str | None = Field(
        default=None,
        description="If risk is medium/high, the attack category (injection, exfiltration, escalation, recon, social_engineering, none)",
    )
    contradicts_memory: bool = Field(
        default=False,
        description="True if the request contradicts established facts in long-term memory",
    )


# ---------------------------------------------------------------------------
# Agent state
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    """The mutable state passed between every node in the graph.

    `total=False` because nodes incrementally populate fields. Each node
    documents which fields it reads and writes.
    """

    # --- Request inputs ---
    request: AccessRequest

    # --- Conversational context (LangGraph short-term memory) ---
    messages: Annotated[list, add_messages]

    # --- Retrieved memory (populated by retrieve_memory node) ---
    relevant_memories: list[dict]

    # --- Pattern detection (populated by pattern_check node) ---
    pattern_score: float
    pattern_signals: list[str]

    # --- LLM validator output (populated by llm_validate node) ---
    llm_validation: LLMValidatorOutput | None

    # --- Procedural rule check (populated by procedural_check node) ---
    procedural_violation: str | None

    # --- Final decision (populated by decide node) ---
    decision: PDPDecision
