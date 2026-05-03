"""Graph nodes for the PDP agent.

Each node is a pure async function that takes (state, store, settings)
and returns a partial state update. This makes them independently testable.

Flow:
    retrieve_memory → pattern_check → procedural_check → llm_validate → decide → write_episodic

The graph in `agent.py` wires these together with conditional routing.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.store.base import BaseStore

from zt_pdp import patterns, procedural, llm_validator, memory
from zt_pdp.config import Settings
from zt_pdp.schemas import (
    AgentState,
    PDPDecision,
    LLMValidatorOutput,
)

logger = logging.getLogger("zt_pdp.nodes")


# ---------------------------------------------------------------------------
# Node 1 — Retrieve memory
# ---------------------------------------------------------------------------

async def retrieve_memory(state: AgentState, store: BaseStore, settings: Settings) -> dict[str, Any]:
    """Pull semantic + episodic memory relevant to the current request.

    READS:  state["request"]
    WRITES: state["relevant_memories"]
    """
    request = state["request"]
    mems = await memory.search_user_memory(
        store=store,
        user_id=request.user_id,
        query=request.prompt,
        k=settings.memory_k,
    )
    logger.debug("retrieve_memory: found %d memories for user=%s", len(mems), request.user_id)
    return {"relevant_memories": mems}


# ---------------------------------------------------------------------------
# Node 2 — Pattern check (cheap, deterministic)
# ---------------------------------------------------------------------------

async def pattern_check(state: AgentState, store: BaseStore, settings: Settings) -> dict[str, Any]:
    """Run regex pattern detection over the request prompt.

    READS:  state["request"]
    WRITES: state["pattern_score"], state["pattern_signals"]
    """
    request = state["request"]
    result = patterns.scan(request.prompt)
    logger.debug(
        "pattern_check: score=%.2f signals=%s", result.score, result.signals
    )
    return {"pattern_score": result.score, "pattern_signals": result.signals}


# ---------------------------------------------------------------------------
# Node 3 — Procedural rule check (hard rules override everything)
# ---------------------------------------------------------------------------

async def procedural_check(state: AgentState, store: BaseStore, settings: Settings) -> dict[str, Any]:
    """Test the request against hard procedural rules.

    If a rule fires, the decision is forced regardless of LLM output.
    This is the auditability layer — rules are deterministic and reviewable.

    READS:  state["request"]
    WRITES: state["procedural_violation"]
    """
    rule = procedural.check(state["request"])
    if rule:
        logger.info("procedural_check: rule triggered: %s", rule.name)
        return {"procedural_violation": rule.reason}
    return {"procedural_violation": None}


# ---------------------------------------------------------------------------
# Node 4 — LLM validator (semantic risk assessment)
# ---------------------------------------------------------------------------

async def llm_validate(state: AgentState, store: BaseStore, settings: Settings) -> dict[str, Any]:
    """Run the LLM-based risk validator with retrieved context.

    READS:  state["request"], state["relevant_memories"], state["pattern_score"], state["pattern_signals"]
    WRITES: state["llm_validation"]
    """
    output = await llm_validator.validate(
        settings=settings,
        request=state["request"],
        memories=state.get("relevant_memories", []),
        pattern_signals=state.get("pattern_signals", []),
        pattern_score=state.get("pattern_score", 0.0),
    )
    logger.debug(
        "llm_validate: risk=%s score=%.2f attack=%s",
        output.risk_assessment,
        output.risk_score,
        output.suspected_attack_type,
    )
    return {"llm_validation": output}


# ---------------------------------------------------------------------------
# Node 5 — Decide (combine signals into final PDPDecision)
# ---------------------------------------------------------------------------

def _combine_risk_score(
    pattern_score: float,
    llm_output: LLMValidatorOutput | None,
) -> float:
    """Fuse pattern and LLM scores into a single risk number.

    Strategy: take the maximum. We are not averaging because a high score
    from either layer is sufficient evidence — a missed signal in one
    layer should not be papered over by the other.
    """
    llm_score = llm_output.risk_score if llm_output else 0.0
    return max(pattern_score, llm_score)


async def decide(state: AgentState, store: BaseStore, settings: Settings) -> dict[str, Any]:
    """Map all collected signals to a final PDPDecision.

    Decision precedence (highest priority first):
    1. Procedural rule violation → DENY
    2. Combined risk_score >= deny_threshold → DENY
    3. Combined risk_score >= stepup_threshold → STEP-UP
    4. Otherwise → ALLOW

    READS:  pattern_score, llm_validation, procedural_violation, relevant_memories
    WRITES: state["decision"]
    """
    procedural_violation = state.get("procedural_violation")
    pattern_score = state.get("pattern_score", 0.0)
    pattern_signals = state.get("pattern_signals", [])
    llm_output: LLMValidatorOutput | None = state.get("llm_validation")
    memories = state.get("relevant_memories", [])

    triggered_signals = list(pattern_signals)
    if llm_output:
        if llm_output.suspected_attack_type:
            triggered_signals.append(f"llm:{llm_output.suspected_attack_type}")
        if llm_output.contradicts_memory:
            triggered_signals.append("llm:contradicts_memory")

    # --- Precedence 1: procedural override ---
    if procedural_violation:
        decision = PDPDecision(
            decision="deny",
            trust_score=0.0,
            risk_score=1.0,
            reason=procedural_violation,
            triggered_signals=triggered_signals + ["procedural_rule"],
            used_memory=bool(memories),
            procedural_override=True,
        )
        return {"decision": decision}

    # --- Precedence 2/3/4: threshold-based ---
    risk = _combine_risk_score(pattern_score, llm_output)
    trust = 1.0 - risk

    if risk >= settings.deny_threshold:
        action = "deny"
        reason = (
            f"Risk score {risk:.2f} exceeds deny threshold {settings.deny_threshold:.2f}. "
            f"{llm_output.reasoning if llm_output else 'Pattern-only detection.'}"
        )
    elif risk >= settings.stepup_threshold:
        action = "step_up"
        reason = (
            f"Risk score {risk:.2f} requires additional verification. "
            f"{llm_output.reasoning if llm_output else 'Pattern-only detection.'}"
        )
    else:
        action = "allow"
        reason = (
            llm_output.reasoning if llm_output
            else "No risk signals triggered."
        )

    decision = PDPDecision(
        decision=action,
        trust_score=trust,
        risk_score=risk,
        reason=reason,
        triggered_signals=triggered_signals,
        used_memory=bool(memories),
        procedural_override=False,
    )
    logger.info(
        "decide: user=%s decision=%s risk=%.2f signals=%s",
        state["request"].user_id,
        action,
        risk,
        triggered_signals,
    )
    return {"decision": decision}


# ---------------------------------------------------------------------------
# Node 6 — Write episodic (feedback loop)
# ---------------------------------------------------------------------------

async def write_episodic(state: AgentState, store: BaseStore, settings: Settings) -> dict[str, Any]:
    """Persist this decision to episodic memory so future requests see it.

    This closes the feedback loop. A user denied for X today affects how
    similar requests from that user score tomorrow.

    READS:  state["request"], state["decision"]
    WRITES: (storage side effect; no state change)
    """
    request = state["request"]
    decision = state["decision"]

    await memory.write_episodic(
        store=store,
        user_id=request.user_id,
        prompt=request.prompt,
        decision=decision.decision,
        risk_score=decision.risk_score,
        reason=decision.reason,
    )
    return {}
