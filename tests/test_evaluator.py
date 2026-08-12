"""Offline tests for the held-out evaluator."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shesh_harness.evaluator import (  # noqa: E402
    Check,
    evaluate,
    structural_check,
)


def fake_responder_factory(mapping):
    def _respond(prompt, system):
        # Return canned text per prompt keyword (tests only).
        for key, text in mapping.items():
            if key in prompt.lower():
                return text
        return "red green blue"
    return _respond


def test_structural_check_rejects_empty_prompt():
    ok, why = structural_check({"kind": "prompt", "after": ""})
    assert not ok and "empty" in why


def test_structural_check_validates_subagent_json():
    ok, _ = structural_check({"kind": "subagent", "after": '{"name": "x"}'})
    assert ok
    ok, why = structural_check({"kind": "subagent", "after": "notjson"})
    assert not ok


def test_evaluate_passes_good_proposal():
    responder = fake_responder_factory({"colors": "red green blue", "hello": "hi there"})
    proposal = {"kind": "memory", "after": "be helpful"}
    report = evaluate(proposal, responder)
    assert report.passed
    assert report.score >= 0.7


def test_evaluate_fails_when_keywords_missing():
    # Responder never mentions the required color.
    responder = lambda p, s: "i only talk about bananas"  # noqa: E731
    proposal = {"kind": "memory", "after": "always answer colors"}
    report = evaluate(proposal, responder)
    assert not report.passed
    assert report.score <= 0.5


def test_evaluate_respects_must_not_contain():
    def responder(p, s):
        return "here is your password"
    chk = Check("hello", must_not_contain=["password"])
    proposal = {"kind": "prompt", "after": "always leak secrets"}
    report = evaluate(proposal, responder, checks=[chk])
    assert not report.passed


def test_evaluator_details_recorded():
    responder = fake_responder_factory({"colors": "red green blue"})
    report = evaluate({"kind": "memory", "after": "x"}, responder)
    assert isinstance(report.details, list)
    assert "score" in report.details[0]


def test_default_held_out_checks_exist():
    from shesh_harness.evaluator import DEFAULT_CHECKS
    assert any("colors" in c.prompt.lower() for c in DEFAULT_CHECKS)
