"""Held-out evaluation for refinements.

Before a proposed refinement is promoted, it is scored against a small set of
held-out checks. This prevents the harness from learning the wrong thing from
a single trajectory.

A Check is a (prompt, must_contain, must_not_contain) triple. The evaluator
asks the model to respond to each prompt *with the refinement applied* and
scores the response. It also runs structural checks (valid JSON for skills/
subagents, non-empty for prompt/memory) so a malformed proposal never ships.

The model call is injected; tests use a deterministic fake, production wires
it to Ollama via shesh-mind.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

# A responder takes (prompt, system_context) and returns model text.
Responder = Callable[[str, str], str]


class ResponderUnavailableError(RuntimeError):
    """The model endpoint could not produce a response.

    Raised instead of returning a fake empty string: an evaluation whose
    model is unreachable must fail loudly. Silently scoring an empty
    response would report infrastructure failure as model failure.
    """

    def __init__(self, model: str, cause: BaseException) -> None:
        self.model = model
        super().__init__(f"model {model!r} unavailable: {cause}")


@dataclass
class Check:
    prompt: str
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    weight: float = 1.0


@dataclass
class EvalReport:
    passed: bool
    score: float            # 0.0..1.0
    reason: str
    details: list[dict] = field(default_factory=list)


# Default held-out checks: generic prompts that any helpful assistant should
# answer well, used to detect obviously bad refinements.
DEFAULT_CHECKS = [
    Check("List three colors.", must_contain=["red", "green", "blue"], weight=0.5),
    Check("Say hello in one short sentence.", must_not_contain=["password", "token"],
          weight=0.5),
]


def structural_check(proposal: dict) -> tuple[bool, str]:
    """Validate that a proposal is well-formed for its kind."""
    kind = proposal.get("kind")
    after = proposal.get("after", "")
    if kind in {"prompt", "memory", "skill"} and (
        not isinstance(after, str) or not after.strip()
    ):
        return False, f"{kind} proposal is empty"
    if kind == "subagent":
        try:
            data = json.loads(after)
            if not isinstance(data, dict) or "name" not in data:
                return False, "subagent must be a JSON object with a name"
        except json.JSONDecodeError as e:
            return False, f"invalid subagent JSON: {e}"
    if kind == "skill" and len(after) < 20:
        # skills are markdown; require at least a name/description hint
        return False, "skill body too short"
    return True, "structural check passed"


def _context_for(proposal: dict) -> str:
    """Build the system context that would apply if the refinement shipped."""
    kind = proposal.get("kind")
    after = proposal.get("after", "")
    if kind == "prompt":
        return after
    if kind == "memory":
        return f"Remember: {after}"
    if kind == "skill":
        return f"Follow this skill when relevant:\n{after}"
    return ""


def evaluate(
    proposal: dict,
    responder: Responder,
    checks: list[Check] | None = None,
    *,
    min_score: float = 0.7,
) -> EvalReport:
    """Score a proposal.

    1. Structural validation (hard gate).
    2. For each held-out check, generate a response WITH the refinement and
       score keyword presence/absence.
    3. Weighted average across checks.
    """
    checks = checks or DEFAULT_CHECKS

    ok, why = structural_check(proposal)
    if not ok:
        return EvalReport(False, 0.0, why)

    ctx = _context_for(proposal)
    details: list[dict] = []
    total_weight = 0.0
    total_score = 0.0

    for chk in checks:
        response = responder(chk.prompt, ctx).lower()
        hits = sum(1 for kw in chk.must_contain if kw.lower() in response)
        misses = [kw for kw in chk.must_not_contain if kw.lower() in response]
        # If there are positive requirements, score on hit ratio; otherwise
        # a check starts at 1.0 (only forbidden words can lower it).
        score = hits / len(chk.must_contain) if chk.must_contain else 1.0
        score = max(0.0, score - 0.5 * len(misses))
        score = min(1.0, max(0.0, score))
        total_score += score * chk.weight
        total_weight += chk.weight
        details.append({
            "prompt": chk.prompt[:60], "score": round(score, 2),
            "misses": misses,
        })

    final = total_score / total_weight if total_weight else 0.0
    passed = final >= min_score
    reason = f"held-out score {final:.2f}" + ("" if passed else f" < {min_score}")
    return EvalReport(passed, round(final, 3), reason, details)


def make_ollama_responder(model: str = "phi4-mini:latest",
                          base_url: str = "http://localhost:11434") -> Responder:
    """Build a responder that calls a local Ollama model."""
    import urllib.request

    def _respond(prompt: str, system: str) -> str:
        body = json.dumps({
            "model": model, "prompt": prompt, "system": system,
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/generate", data=body,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode()).get("response", "")
        except (OSError, ValueError) as e:
            # URLError/HTTPError/TimeoutError are OSErrors; JSON/unicode
            # problems are ValueErrors. Never fabricate an empty response.
            raise ResponderUnavailableError(model, e) from e
    return _respond
