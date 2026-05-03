"""Render the agent's LangGraph topology as a PNG.

Useful for the assignment screenshot showing the agent design.

Usage:
    uv run python scripts/render_graph.py
    open docs/agent_graph.png
"""

from __future__ import annotations

from pathlib import Path

from zt_pdp.agent import build_agent
from zt_pdp.config import Settings
from zt_pdp.memory import build_store


def main() -> None:
    settings = Settings(
        openai_api_key="sk-render-only",
        llm_model="gpt-4o-mini",
        memory_model="gpt-4o-mini",
        embedding_model="text-embedding-3-small",
        embedding_dims=1536,
        deny_threshold=0.75,
        stepup_threshold=0.45,
        session_window=8,
        memory_k=5,
        llm_validate_always=False,
        debug=False,
    )
    store = build_store(settings)
    agent = build_agent(store, settings)

    out_dir = Path(__file__).resolve().parents[1] / "docs"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "agent_graph.png"

    # LangGraph offers two render paths — Mermaid (text) and PNG via Mermaid.ink
    png_bytes = agent.get_graph().draw_mermaid_png()
    out_path.write_bytes(png_bytes)
    print(f"✅ wrote {out_path}")

    mermaid_path = out_dir / "agent_graph.mmd"
    mermaid_path.write_text(agent.get_graph().draw_mermaid())
    print(f"✅ wrote {mermaid_path}")


if __name__ == "__main__":
    main()
