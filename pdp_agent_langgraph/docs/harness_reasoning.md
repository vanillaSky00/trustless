# Harness Engineering — Reasoning Document

**Tags:** #zero-trust #agent #harness #langgraph #week8 #task3

> The Task 3 rubric explicitly asks: *"Based on your system design, think about and implement harness engineering to validate and evaluate the agent's behavior and decision-making ability, and document your reasoning process."* This document is that reasoning.

---

## What is a harness, and why does this agent need one?

A **test harness** is a structured set of inputs + expected outputs used to validate that a system behaves correctly across many cases — not just on the example you happened to write. For an autonomous agent, the harness is what separates "it worked once when I tried it" from "I have evidence the system is reliable."

For a Zero Trust PDP specifically, the harness is the **trust mechanism for the agent itself**. We are asking the agent to make security decisions — but how do we trust *it*? Answer: we don't trust it; we *verify* it. The harness operationalizes "never trust, always verify" recursively — applied to the agent rather than to the user the agent is judging.

This is the same principle that motivates Zero Trust in the first place. A clean recursive design.

---

## Design principle 1 — Scenarios, not data points

Naive harnesses test individual decisions: input X → expected output Y. That works for stateless classifiers but **misses the entire point of a stateful, memory-aware agent**. A stateful agent's behaviour on request N depends on requests 1..N-1.

So scenarios in this harness are **sequences**, not single inputs. Each scenario is:

- A user_id (memory is scoped per-user)
- A list of steps, each with an expected decision
- Optional pre-seeded semantic memories (for "user previously asserted X" setups)
- Invariants that must hold across the whole sequence

This lets us test claims that no single decision could prove. Example: "after a denial, the next similar request should also be denied AND should cite episodic memory." That's a two-step assertion across one user — impossible to test with isolated requests.

---

## Design principle 2 — Test architectural claims, not implementation details

Each scenario is designed to validate one specific claim about the architecture:

| Scenario | Architectural claim being tested |
|---|---|
| S1 | The agent doesn't false-positive on benign use (no over-blocking) |
| S2 | Pattern detection catches the easy 80% of attacks |
| S3 | Multi-turn attacks are caught — pattern + LLM + memory together |
| S4 | Procedural rules override LLM judgement (auditability layer works) |
| S5 | Episodic memory genuinely contributes to subsequent decisions |
| S6 | The agent is robust against memory poisoning from upstream PIPs |
| S7 | Procedural rules cover unauthenticated edge cases |

If a scenario fails, you know exactly which architectural claim is broken. This is more valuable than a flat accuracy number — pass rates don't tell you *what* failed.

---

## Design principle 3 — Use real LLM calls in the harness, mock in unit tests

There are two test layers in this project, intentionally:

**Unit tests (`tests/`)** — mock the LLM, run in milliseconds, used to verify graph wiring, decision logic, and memory plumbing. Free, fast, run on every commit.

**Harness (`harness.py`)** — use the real LLM, run end-to-end. Used to validate the *integrated* system makes sensible decisions. Costs money per run (a few cents per scenario at gpt-4o-mini prices).

Mixing these would be a mistake in either direction:
- Mocking the LLM in the harness means we never validate the LLM actually understands the prompts we send it.
- Using the real LLM in unit tests means a flaky network kills CI and every test costs money.

The harness output is what gets screenshotted for the assignment; unit tests are for development hygiene.

---

## What the harness measures

For each scenario, the harness reports:

- **Per-step pass/fail** — did each individual decision match the expected one?
- **Risk score evolution** — how did the score change across the sequence?
- **Memory usage** — did the agent consult retrieved memories?
- **Procedural override** — did a hard rule fire?
- **Triggered signals** — what specific patterns/LLM signals contributed?
- **Invariant satisfaction** — did sequence-level properties hold?
- **Overall pass** — all per-step expectations + all invariants

The JSON output (`harness_results.json`) is structured so it can be:
- Diffed across runs to detect regressions
- Compared across configurations (e.g., LLM_VALIDATE_ALWAYS on vs off)
- Summarized into the metrics needed for the assignment write-up

---

## What the harness does NOT measure (limitations)

Honest documentation of what the harness *can't* tell us:

1. **Adaptive attackers** — every scenario is a static sequence. A real attacker would adapt based on what the PDP rejected; the harness doesn't simulate that. Mitigation would be adversarial fuzzing — out of scope here.
2. **Concept drift** — the harness uses a fresh memory store per scenario. We don't test what happens when memories accumulate over weeks of normal use.
3. **Latency / throughput** — the harness measures correctness, not performance. A real PDP has hard latency budgets (NIST guidance suggests <100ms); we don't enforce that here.
4. **LLM nondeterminism** — same prompt, different temperature, possibly different score. We use temperature=0.1 to minimize this but don't run multiple seeds per scenario. A production harness would.
5. **Memory injection attacks** — what if an attacker can write directly to the memory store (e.g., via a compromised PIP)? S6 partially tests this via `seed_memories`, but a complete test would simulate adversarial memory writes alongside requests.

These limitations are not failures of the design — they're explicit boundaries that make the harness's positive results meaningful. The scope is "validate the architectural claims of the agent under controlled conditions," not "prove the system is unhackable."

---

## What "passing" actually means

A scenario passes if:
1. Every step's actual decision matches the expected decision, AND
2. Every invariant function returns True

A scenario can fail in three distinct ways:
- **Per-step mismatch** — the decision was wrong (e.g., expected deny, got allow)
- **Invariant violation** — decisions individually correct but sequence property broken (e.g., risk score didn't increase across an escalating attack)
- **Both** — clear architectural problem

The distinction matters for debugging. A per-step mismatch tells you the decision logic is wrong for a specific input. An invariant violation tells you the *integration* across steps is wrong even though individual decisions look fine.

---

## How to read the harness output

The console output uses a per-scenario table:

```
▶ Running S3-slow-burn-escalation — Reconnaissance → escalation → exfiltration sequence...
┌───┬──────────┬──────────┬──────┬─────┬──────┬─────────────────────┬──────┐
│ # │ Expected │ Actual   │ Risk │ Mem │ Proc │ Signals             │ Pass │
├───┼──────────┼──────────┼──────┼─────┼──────┼─────────────────────┼──────┤
│ 0 │ allow    │ allow    │ 0.10 │  ·  │  ·   │ llm:none            │  ✅  │
│ 1 │ allow    │ allow    │ 0.20 │  ✓  │  ·   │ llm:none            │  ✅  │
│ 2 │ step_up  │ step_up  │ 0.50 │  ✓  │  ·   │ privilege_escalation│  ✅  │
│ 3 │ deny     │ deny     │ 0.95 │  ✓  │  ·   │ exfiltration, ...   │  ✅  │
└───┴──────────┴──────────┴──────┴─────┴──────┴─────────────────────┴──────┘
  Invariants: ✅ passed, Overall: ✅
```

Read it as: each row is a step in the sequence, columns show what the agent decided and why. The Mem column shows whether memory was consulted; the Proc column shows whether a procedural rule fired. A scenario with all green checkmarks AND green invariants is a confirmed pass.

---

## What to capture for the assignment

For Task 3, the recommended screenshots are:

1. **`docs/agent_graph.png`** — the LangGraph topology (workflow diagram required by rubric)
2. **Console output of `uv run zt-harness`** — the seven scenario tables + summary
3. **One detailed scenario** — S3 (slow-burn) is the most architecturally compelling because it shows risk score evolution across a real LLM-mediated decision sequence
4. **`harness_results.json`** snippet — structured output proving the harness produces machine-readable artifacts (relevant for CI integration discussion)

Writing the report, lead with: *"The harness validates seven distinct architectural claims about the agent. Each claim is encoded as a multi-step scenario with per-step expectations and sequence-level invariants. Pass rate is X/7."*

---

## Reasoning summary

The harness is the answer to "how do I know this agent works?" It's not a proof — it's evidence. The evidence is structured: each scenario tests a specific claim, each claim is one architectural commitment, and overall pass rate is the integral of all those commitments holding together. Failing scenarios point precisely at which commitment broke.

This is the engineering counterpart to the Zero Trust principle the agent itself enforces. The agent verifies users; the harness verifies the agent. Trust at no level is assumed — it's continuously demonstrated.
