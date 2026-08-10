# shesh-harness

**Continual Harness for self-improvement** — Evidence-backed refinements with rollback; base prompt immutable.

- Layer: Mind (Mind)
- License: GPL-3.0
- Part of: [Shesh ecosystem](https://github.com/gaganjainse/shesh-ecosystem)

---
**Continual Harness for safe self-improvement.**

Implements the Prime Agent `/refine` pattern with hard guardrails:

- The **base system prompt and safety skills are immutable**.
- Supplemental state (prompt notes, memories, skills, subagent specs) is a CRUD
  surface the agent can refine through small, evidence-backed edits.
- Every refinement is append-only with trigger, before/after, score, and outcome;
  any change can be **reverted by ID**.
- Refinements are evaluated before applying (pluggable planner + evaluator;
  production wires in a local LLM + `llm-eval-harness`).

- License: GPL-3.0
- Layer: Mind
- Part of: [Shesh ecosystem](https://github.com/gaganjainse/shesh-ecosystem)

## Why this exists

A self-improving agent that can edit its own prompt without guardrails will
overfit metrics (the Prime "Factorio cheating" result). This harness keeps the
base prompt immutable, requires evidence/evaluation, supports rollback, and
promotes changes only after they pass tests — so the system can learn your
intentions and mannerisms without destabilizing itself.

## Tools (MCP, stdio)

- `get_prompt_block()` — supplemental prompt + memories for the turn
- `add_memory(text)` / `upsert_skill(name, body)` / `list_skills()`
- `refine(trigger, trajectory)` — propose, evaluate, and apply a small change
- `list_refinements()` / `revert_refinement(id)`

## Develop

```bash
uv sync --extra dev
uv run pytest -q          # 7 offline tests (no LLM needed)
uv run ruff check .
uv run shesh-harness-mcp
```

State lives under `~/.local/share/shesha/harness/` (`state.json`,
`refinements.jsonl`) — plain JSON, editable, versionable.