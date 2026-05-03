"""Long-term memory using LangGraph InMemoryStore + LangMem tools.

This module wires the persistent memory layer the agent uses:
- Semantic memory: facts about users (e.g., "user is a security analyst")
- Episodic memory: past PDP decisions (e.g., "denied user X for action Y")

We intentionally use the official packages rather than rolling our own:
- `langgraph.store.memory.InMemoryStore` for storage with embedding index
- `langmem.create_manage_memory_tool` / `create_search_memory_tool` for agent tools

The agent doesn't directly call these tools — it queries them via helper
functions in this module. This keeps the agent code clean and lets us swap
the storage backend later (e.g., to Postgres) without touching node code.
"""

from __future__ import annotations

from typing import Any

from langgraph.store.memory import InMemoryStore

from zt_pdp.config import Settings


# Namespaces — keep memory types separated so we never mix decisions with
# user-asserted facts. The (kind, user_id) tuple structure means a user's
# semantic facts are isolated from another user's facts.
SEMANTIC_NS = ("semantic",)        # ("semantic", user_id) — facts about users
EPISODIC_NS = ("episodic",)        # ("episodic", user_id) — past decisions for user


def build_store(settings: Settings) -> InMemoryStore:
    """Create the InMemoryStore configured with semantic embedding search.

    `dims` and `embed` must match the embedding model in settings. LangMem
    uses these for vector search inside `create_search_memory_tool`.
    """
    return InMemoryStore(
        index={
            "dims": settings.embedding_dims,
            "embed": f"openai:{settings.embedding_model}",
        }
    )


# ---------------------------------------------------------------------------
# Helpers for the agent nodes
# ---------------------------------------------------------------------------

async def search_user_memory(
    store: InMemoryStore,
    user_id: str,
    query: str,
    k: int = 5,
) -> list[dict[str, Any]]:
    """Semantic search over a user's memories — both semantic and episodic.

    Returns the top-k most relevant entries as plain dicts for the agent
    state. Mixing semantic and episodic in one search lets the LLM see
    both who the user is AND what they have done before.

    Failures (no memories, embedding API errors) return an empty list rather
    than raising — a memory miss should never crash the PDP.
    """
    results: list[dict[str, Any]] = []

    for ns in (SEMANTIC_NS + (user_id,), EPISODIC_NS + (user_id,)):
        try:
            items = await store.asearch(ns, query=query, limit=k)
        except Exception:
            # Empty namespace, embedding service down, etc. — degrade gracefully
            continue
        for item in items:
            results.append({
                "kind": ns[0],
                "key": item.key,
                "value": item.value,
                "score": getattr(item, "score", None),
            })

    # Sort by score descending if scores are available
    results.sort(key=lambda x: x.get("score") or 0.0, reverse=True)
    return results[:k]


async def write_episodic(
    store: InMemoryStore,
    user_id: str,
    *,
    prompt: str,
    decision: str,
    risk_score: float,
    reason: str,
) -> None:
    """Record a PDP decision into the user's episodic memory.

    Episodic memories are what let the agent recognize repeat offenders:
    "this user has been denied 3 times for similar requests" is exactly
    the signal a stateful PDP needs.

    Failures are swallowed — a memory write failure should never break the
    enforcement decision (which has already been made by the time we get here).
    """
    ns = EPISODIC_NS + (user_id,)
    # Use a deterministic-ish key based on time so chronology is preserved
    import time
    key = f"decision-{int(time.time() * 1000)}"

    try:
        await store.aput(
            ns,
            key,
            {
                "prompt": prompt[:500],  # truncate to keep storage bounded
                "decision": decision,
                "risk_score": risk_score,
                "reason": reason,
                "ts": time.time(),
            },
        )
    except Exception:
        # Embedding service failure / network issue — log but don't block
        # the decision that has already been delivered.
        pass


async def seed_semantic(
    store: InMemoryStore,
    user_id: str,
    fact: str,
    *,
    source: str = "harness",
) -> None:
    """Seed a semantic fact about a user.

    Used by the harness to set up "the user previously stated X" scenarios
    without requiring a full conversation to extract the fact via LLM.
    Production code would write semantic memories via LangMem's extraction
    tools; this helper is for reproducible testing.
    """
    ns = SEMANTIC_NS + (user_id,)
    import time
    key = f"fact-{int(time.time() * 1000)}"
    try:
        await store.aput(
            ns,
            key,
            {"fact": fact, "source": source, "ts": time.time()},
        )
    except Exception:
        pass
