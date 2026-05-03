"""LangGraph state machine for the Zero Trust PDP agent.

The graph topology:

    START
      │
      ▼
   retrieve_memory  ─────┐
      │                  │  (semantic + episodic memory loaded)
      ▼                  │
   pattern_check         │  (cheap regex scan)
      │                  │
      ▼                  │
   procedural_check      │  (hard rules check)
      │                  │
      ▼                  │
   ┌──────────────────┐  │
   │ Should we call   │  │
   │ the LLM?         │  │
   └────────┬─────────┘  │
            │            │
   ┌────────┴────────┐   │
   │                 │   │
   ▼                 ▼   │
 llm_validate    skip_llm│
   │                 │   │
   └────────┬────────┘   │
            ▼            │
         decide ─────────┘
            │
            ▼
       write_episodic
            │
            ▼
           END

The conditional skip_llm path lets us avoid an LLM call when:
- A procedural rule already fired (decision is forced)
- Pattern score is so low (< stepup_threshold/2) AND LLM_VALIDATE_ALWAYS=false
  that there is nothing for the LLM to add
"""

from __future__ import annotations

from langgraph.graph import StateGraph, START, END
from langgraph.store.base import BaseStore

from zt_pdp import nodes
from zt_pdp.config import Settings
from zt_pdp.schemas import AgentState


def _should_run_llm(state: AgentState, settings: Settings) -> str:
    """Conditional edge: decide whether the LLM validator runs.

    Returns the name of the next node:
        "llm_validate" if LLM should run
        "decide"       if LLM should be skipped
    """
    # If a procedural rule fired, skip the LLM — decision is forced regardless.
    if state.get("procedural_violation"):
        return "decide"

    # If patterns are clearly suspicious, the LLM call is worth the cost.
    pattern_score = state.get("pattern_score", 0.0)
    if pattern_score >= settings.stepup_threshold / 2:
        return "llm_validate"

    # Globally force-on flag for benchmarking
    if settings.llm_validate_always:
        return "llm_validate"

    # Pattern score is very low and no other signals — skip LLM, save cost
    return "decide"


def build_agent(store: BaseStore, settings: Settings):
    """Construct the compiled LangGraph agent.

    The store is passed in (not constructed here) so the harness can:
    - Pre-seed semantic facts before running scenarios
    - Inspect memory after a run for assertions
    - Reuse the same store across multiple invocations to test LTM persistence
    """

    # Wrap node functions to inject store + settings without polluting state
    async def _retrieve(state: AgentState):
        return await nodes.retrieve_memory(state, store, settings)

    async def _patterns(state: AgentState):
        return await nodes.pattern_check(state, store, settings)

    async def _procedural(state: AgentState):
        return await nodes.procedural_check(state, store, settings)

    async def _llm(state: AgentState):
        return await nodes.llm_validate(state, store, settings)

    async def _decide(state: AgentState):
        return await nodes.decide(state, store, settings)

    async def _write(state: AgentState):
        return await nodes.write_episodic(state, store, settings)

    graph = StateGraph(AgentState)

    graph.add_node("retrieve_memory", _retrieve)
    graph.add_node("pattern_check", _patterns)
    graph.add_node("procedural_check", _procedural)
    graph.add_node("llm_validate", _llm)
    graph.add_node("decide", _decide)
    graph.add_node("write_episodic", _write)

    # Linear prefix
    graph.add_edge(START, "retrieve_memory")
    graph.add_edge("retrieve_memory", "pattern_check")
    graph.add_edge("pattern_check", "procedural_check")

    # Conditional: should we run the LLM, or jump straight to decide?
    graph.add_conditional_edges(
        "procedural_check",
        lambda state: _should_run_llm(state, settings),
        {"llm_validate": "llm_validate", "decide": "decide"},
    )

    graph.add_edge("llm_validate", "decide")
    graph.add_edge("decide", "write_episodic")
    graph.add_edge("write_episodic", END)

    return graph.compile()
