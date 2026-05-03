"""Interactive CLI — paste a prompt, see the PDP decision.

Useful for live demos and ad-hoc testing. Maintains a single in-memory
store across prompts so memory accumulation is observable.

Usage:
    uv run zt-cli                       # interactive REPL
    uv run zt-cli --user vanillasky     # specify user_id
    uv run zt-cli --role intern         # specify asserted role
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from rich.console import Console
from rich.panel import Panel

from zt_pdp.agent import build_agent
from zt_pdp.config import Settings
from zt_pdp.memory import build_store
from zt_pdp.schemas import AccessRequest, PDPDecision

console = Console()


def _format_decision(decision: PDPDecision) -> Panel:
    color_map = {"allow": "green", "step_up": "yellow", "deny": "red"}
    color = color_map.get(decision.decision, "white")
    body = (
        f"[bold]{decision.decision.upper()}[/bold]  "
        f"risk={decision.risk_score:.2f}  trust={decision.trust_score:.2f}\n\n"
        f"[dim]Reason:[/dim] {decision.reason}\n"
        f"[dim]Signals:[/dim] {', '.join(decision.triggered_signals) or '(none)'}\n"
        f"[dim]Memory used:[/dim] {decision.used_memory}  "
        f"[dim]Procedural override:[/dim] {decision.procedural_override}"
    )
    return Panel(body, border_style=color, title="PDP Decision", title_align="left")


async def run_repl(user_id: str, role: str | None) -> None:
    settings = Settings.from_env()
    store = build_store(settings)
    agent = build_agent(store, settings)

    console.print(Panel.fit(
        f"[bold]ZT PDP Agent[/bold] — user=[cyan]{user_id}[/cyan] role=[cyan]{role or 'none'}[/cyan]\n"
        f"Type a prompt to test. Type [bold]quit[/bold] to exit.",
        border_style="blue",
    ))

    while True:
        try:
            prompt = console.input("\n[bold]>[/bold] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye.[/dim]")
            return

        if not prompt or prompt.lower() in {"quit", "exit", "q"}:
            return

        request = AccessRequest(user_id=user_id, prompt=prompt, user_role=role)
        final_state = await agent.ainvoke({"request": request})
        decision: PDPDecision = final_state["decision"]

        console.print(_format_decision(decision))


def main() -> int:
    parser = argparse.ArgumentParser(description="ZT PDP Agent — interactive CLI")
    parser.add_argument("--user", default="demo-user", help="User ID for the session")
    parser.add_argument("--role", default=None, help="Asserted role (treated as untrusted)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    asyncio.run(run_repl(args.user, args.role))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
