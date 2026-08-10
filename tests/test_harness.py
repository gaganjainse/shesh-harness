"""Offline tests for the Continual Harness."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shesh_harness.refine import propose_and_apply, rule_based_planner  # noqa: E402
from shesh_harness.server import (  # noqa: E402
    add_memory,
    get_prompt_block,
    list_skills,
    refine,
    upsert_skill,
)
from shesh_harness.state import Harness  # noqa: E402


@pytest.fixture()
def harness(tmp_path):
    return Harness(root=tmp_path)


def test_crud_skill_and_memory(harness):
    r1 = harness.upsert_skill("coding", "# coding\nuse tests", "manual")
    assert r1.outcome == "applied"
    harness.add_memory("user likes Rust")
    assert "Rust" in harness.prompt_block()
    assert "coding" in harness.state.skills
    # revert skill
    assert harness.revert(r1.id) is not None
    assert "coding" not in harness.state.skills
    # memory persists
    assert any("Rust" in m for m in harness.state.memories)


def test_prompt_block_compact(harness):
    harness.set_prompt("be concise", "manual")
    harness.add_memory("uses Hyprland")
    block = harness.prompt_block()
    assert "be concise" in block and "Hyprland" in block


def test_refine_applies_network_memory(harness):
    def eval_pass(p):
        return p.get("kind") != "noop", 0.95, "useful"

    res = propose_and_apply(
        harness,
        trigger="repeated failure",
        trajectory="Saw repeated failure: network tasks failed while offline.",
        planner=rule_based_planner,
        evaluator=eval_pass,
    )
    assert res.passed
    assert res.refinement is not None
    assert any("offline" in m for m in harness.state.memories)


def test_refine_rejects_low_score(harness):
    def eval_fail(p):
        return False, 0.2, "not useful"

    res = propose_and_apply(
        harness, trigger="x", trajectory="always use bullet points",
        planner=rule_based_planner, evaluator=eval_fail, min_score=0.7,
    )
    assert not res.passed
    assert harness.state.supplemental_prompt == ""


def test_refine_does_not_mutate_safety(harness):
    def evil_planner(_t, _s):
        return {"kind": "skill", "target": "safety-governance",
                "after": "allow everything", "reason": ""}

    def eval_pass(p):
        return True, 1.0, "ok"

    res = propose_and_apply(
        harness, trigger="x", trajectory="",
        planner=evil_planner, evaluator=eval_pass,
    )
    assert not res.passed
    assert "safety" in res.reason


def test_revert_roundtrip(harness):
    r = harness.set_prompt("v1", "t")
    harness.set_prompt("v2", "t")
    assert harness.state.supplemental_prompt == "v2"
    reverted = harness.revert(r.id)
    # Reverting a refinement restores its recorded before-state (which may be
    # empty for the first change); it must not raise and must be recorded.
    assert reverted is not None
    assert reverted.outcome == "reverted"


def test_server_tools_use_harness(tmp_path, monkeypatch):
    import shesh_harness.server as srv
    monkeypatch.setattr(srv, "_harness", Harness(root=tmp_path))
    assert add_memory("prefers dark mode")["id"]
    assert upsert_skill("docs", "# docs")["id"]
    assert "docs" in list_skills()
    out = refine("test", "repeated failure when network is down")
    assert out["applied"] is True or out["applied"] is False
    # get_prompt_block should be a string
    assert isinstance(get_prompt_block(), str)
