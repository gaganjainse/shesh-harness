"""MCP server exposing the Continual Harness."""
from __future__ import annotations

from shesh_audit.mcp_guard import GuardedMCP as _MCP

from .refine import (
    Evaluator,
    Planner,
    RefineResult,
    propose_and_apply,
    rule_based_planner,
)
from .state import Harness

mcp = _MCP("shesh-harness")

_harness: Harness | None = None


def _get_harness() -> Harness:
    global _harness
    if _harness is None:
        _harness = Harness()
    return _harness


@mcp.tool()
def get_prompt_block() -> str:
    """Return the supplemental prompt + memories to add to the model context."""
    return _get_harness().prompt_block()


@mcp.tool()
def add_memory(memory: str) -> dict:
    """Add a durable memory to the harness."""
    r = _get_harness().add_memory(memory, trigger="agent")
    return {"id": r.id, "kind": r.kind}


@mcp.tool()
def upsert_skill(name: str, body: str) -> dict:
    """Create or update a reusable skill (Markdown)."""
    r = _get_harness().upsert_skill(name, body, trigger="agent")
    return {"id": r.id, "target": r.target}


@mcp.tool()
def list_skills() -> list[str]:
    return sorted(_get_harness().state.skills)


@mcp.tool()
def list_refinements(limit: int = 20) -> list[dict]:
    if limit < 0:
        return []
    return [
        {"id": r.id, "kind": r.kind, "target": r.target,
         "outcome": r.outcome, "score": r.score, "ts": r.ts}
        for r in _get_harness().refinements[-limit:]
    ]


@mcp.tool()
def revert_refinement(ref_id: str) -> dict:
    r = _get_harness().revert(ref_id)
    return {"ok": r is not None, "id": ref_id}


@mcp.tool()
def refine(trigger: str, trajectory: str, min_score: float = 0.7) -> dict:
    """Propose a refinement, but never auto-approve without a real evaluator.

    The previous implementation used an ``always_pass`` evaluator that assigned
    score 0.9 to every non-noop proposal and immediately mutated persistent
    harness state. That contradicted the module's evidence-backed refinement
    contract. The non-LLM tool now remains proposal-safe; real promotion goes
    through ``refine_with_llm`` (or an injected evaluator in tests).
    """
    planner: Planner = rule_based_planner
    result: RefineResult = propose_and_apply(
        _get_harness(),
        trigger,
        trajectory,
        planner,
        evaluator=None,
        responder=None,
        min_score=min_score,
    )
    return {
        "applied": result.passed,
        "score": result.score,
        "reason": result.reason,
        "refinement": result.refinement.id if result.refinement else None,
    }


@mcp.tool()
def refine_with_llm(trigger: str, trajectory: str, model: str = "phi4-mini:latest",
                    min_score: float = 0.7) -> dict:
    """Run /refine using a local Ollama model as planner and held-out evaluator.

    Falls back to the rule-based planner if Ollama is unreachable.
    """
    from .evaluator import make_ollama_responder
    from .refine import (
        default_evaluator,
        propose_and_apply,
        rule_based_planner,
    )
    try:
        responder = make_ollama_responder(model)
        evaluator = default_evaluator(responder, min_score=min_score)
        result = propose_and_apply(
            _get_harness(), trigger, trajectory, rule_based_planner,
            evaluator, min_score=min_score,
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    return {
        "ok": result.passed, "score": result.score,
        "reason": result.reason,
        "applied": result.refinement is not None,
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
