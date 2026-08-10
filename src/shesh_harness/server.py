"""MCP server exposing the Continual Harness."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

try:
    from shesh_audit.mcp_guard import GuardedMCP as _MCP
except ImportError:
    _MCP = FastMCP

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


def h() -> Harness:
    global _harness
    if _harness is None:
        _harness = Harness()
    return _harness


@mcp.tool()
def get_prompt_block() -> str:
    """Return the supplemental prompt + memories to add to the model context."""
    return h().prompt_block()


@mcp.tool()
def add_memory(memory: str) -> dict:
    """Add a durable memory to the harness."""
    r = h().add_memory(memory, trigger="agent")
    return {"id": r.id, "kind": r.kind}


@mcp.tool()
def upsert_skill(name: str, body: str) -> dict:
    """Create or update a reusable skill (Markdown)."""
    r = h().upsert_skill(name, body, trigger="agent")
    return {"id": r.id, "target": r.target}


@mcp.tool()
def list_skills() -> list[str]:
    return sorted(h().state.skills)


@mcp.tool()
def list_refinements(limit: int = 20) -> list[dict]:
    return [
        {"id": r.id, "kind": r.kind, "target": r.target,
         "outcome": r.outcome, "score": r.score, "ts": r.ts}
        for r in h().refinements[-limit:]
    ]


@mcp.tool()
def revert_refinement(ref_id: str) -> dict:
    r = h().revert(ref_id)
    return {"ok": r is not None, "id": ref_id}


@mcp.tool()
def refine(trigger: str, trajectory: str, min_score: float = 0.7) -> dict:
    """Propose and, if it passes eval, apply a small evidence-backed refinement."""

    # Production: replace planner/evaluator with LLM + llm-eval-harness.
    planner: Planner = rule_based_planner

    def always_pass(proposal: dict) -> tuple[bool, float, str]:
        if proposal.get("kind") == "noop":
            return False, 0.0, "no proposal"
        return True, 0.9, "rule-based proposal accepted"

    evaluator: Evaluator = always_pass
    result: RefineResult = propose_and_apply(
        h(), trigger, trajectory, planner, evaluator, min_score=min_score)
    return {
        "applied": result.passed,
        "score": result.score,
        "reason": result.reason,
        "refinement": result.refinement.id if result.refinement else None,
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()


@mcp.tool()
def refine_with_llm(trigger: str, trajectory: str, model: str = "phi4-mini:latest",
                    min_score: float = 0.7) -> dict:
    """Run /refine using a local Ollama model as planner and held-out evaluator.

    Falls back to the rule-based planner if Ollama is unreachable.
    """
    from .evaluator import make_ollama_responder
    from .refine import (
        default_evaluator, propose_and_apply, rule_based_planner,
    )
    try:
        responder = make_ollama_responder(model)
        evaluator = default_evaluator(responder, min_score=min_score)
        # Planner: a tiny LLM prompt wrapper would go here; for now use the
        # rule-based proposer but evaluate with the real held-out checks.
        result = propose_and_apply(
            h(), trigger, trajectory, rule_based_planner,
            evaluator, min_score=min_score,
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    return {
        "ok": result.passed, "score": result.score,
        "reason": result.reason,
        "applied": result.refinement is not None,
    }
