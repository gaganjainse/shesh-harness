"""/refine: propose the smallest evidence-backed improvement to harness state.

The refinement is intentionally conservative:
- It operates only on supplemental state, never the base prompt or safety skills.
- A proposal is scored on a held-out check before promotion.
- Every change is recorded with trigger + outcome and can be reverted.

The actual LLM call is injected (so tests don't need a model). In production the
planner is a local Ollama model; the eval is the user's llm-eval-harness.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from .state import Harness, Refinement

# A planner takes (trajectory summary, current state) and returns a proposal dict:
#   {"kind": "...", "target": "...", "after": "...", "reason": "..."}
Planner = Callable[[str, dict], dict]
# An evaluator takes (proposal) and returns (passed: bool, score: float, reason: str)
Evaluator = Callable[[dict], tuple[bool, float, str]]


@dataclass
class RefineResult:
    refinement: Refinement | None
    passed: bool
    score: float
    reason: str


def propose_and_apply(
    harness: Harness,
    trigger: str,
    trajectory: str,
    planner: Planner,
    evaluator: Evaluator,
    *,
    min_score: float = 0.7,
) -> RefineResult:
    """Plan a refinement, evaluate it, and apply only if it passes."""
    proposal = planner(trajectory, _snapshot(harness))
    kind = proposal.get("kind")
    target = proposal.get("target")
    after = proposal.get("after", "")
    if kind not in {"prompt", "skill", "memory", "subagent"} or not target:
        return RefineResult(None, False, 0.0, "invalid proposal")
    if kind == "skill" and target in {"safety-governance"}:
        return RefineResult(None, False, 0.0, "cannot refine safety skills")

    # Evaluate before mutating persistent state.
    passed, score, reason = evaluator(proposal)
    if not passed or score < min_score:
        return RefineResult(None, False, score, reason)

    # Apply via the CRUD surface (records the refinement).
    if kind == "prompt":
        r = harness.set_prompt(after, trigger)
    elif kind == "skill":
        r = harness.upsert_skill(target, after, trigger)
    elif kind == "memory":
        r = harness.add_memory(after, trigger)
    else:
        r = harness.upsert_subagent(target, json.loads(after), trigger)
    r.score = score
    r.outcome = f"applied: {reason}"
    harness._write_refinements()  # persist updated score/outcome
    return RefineResult(r, True, score, reason)


def _snapshot(h: Harness) -> dict:
    return {
        "supplemental_prompt": h.state.supplemental_prompt,
        "skills": sorted(h.state.skills),
        "memories": h.state.memories,
        "subagents": sorted(h.state.subagents),
    }


def rule_based_planner(trajectory: str, _state: dict) -> dict:
    """A tiny offline planner used for tests and as a safe fallback.

    If the trajectory mentions a repeated failure with a known pattern, propose
    a memory note; otherwise no-op.
    """
    t = trajectory.lower()
    if "repeated failure" in t and "network" in t:
        return {
            "kind": "memory",
            "target": "list",
            "after": "Network-dependent tasks should skip and retry when offline.",
            "reason": "observed repeated network failures",
        }
    if "always use bullet" in t:
        return {
            "kind": "prompt",
            "target": "supplemental",
            "after": "Format responses as concise bullet points unless asked otherwise.",
            "reason": "explicit user preference observed",
        }
    return {"kind": "noop", "target": "", "after": "", "reason": "no improvement found"}
