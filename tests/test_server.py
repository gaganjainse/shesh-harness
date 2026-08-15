"""Smoke tests for the harness MCP server — every tool callable, right schema.

Isolation: the harness is pointed at a temp dir and the LLM responder is
stubbed out so refine_with_llm exercises its deterministic fallback path.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shesh_harness import server  # noqa: E402
from shesh_harness.state import Harness  # noqa: E402

EXPECTED_TOOLS = {
    "get_prompt_block", "add_memory", "upsert_skill", "list_skills",
    "list_refinements", "revert_refinement", "refine", "refine_with_llm",
}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_harness", Harness(root=tmp_path))
    yield


def test_all_tools_registered():
    import asyncio
    registered = {t.name for t in asyncio.run(server.mcp.list_tools())}
    missing = EXPECTED_TOOLS - registered
    assert not missing, f"unregistered tools: {sorted(missing)}"


def test_prompt_block_is_str():
    assert isinstance(server.get_prompt_block(), str)


def test_memory_skill_refinement_cycle():
    mem = server.add_memory("prefers terse replies")
    assert set(mem) == {"id", "kind"}
    skill = server.upsert_skill("deploy", "# deploy steps")
    assert set(skill) == {"id", "target"}
    assert "deploy" in server.list_skills()
    refs = server.list_refinements()
    assert refs and all(set(r) == {"id", "kind", "target", "outcome", "score", "ts"}
                        for r in refs)
    assert server.revert_refinement(mem["id"])["ok"] is True


def test_refine_rule_based_schema():
    out = server.refine("test", "repeated failure when the network is down")
    assert set(out) == {"applied", "score", "reason", "refinement"}
    assert isinstance(out["applied"], bool)
    assert isinstance(out["score"], float)


def test_refine_with_llm_falls_back_offline(monkeypatch):
    # Simulate unreachable Ollama: the responder constructor raises, which the
    # tool's try/except turns into a structured error result (never a crash).
    class NoOllama(OSError):
        def __init__(self) -> None:
            super().__init__("no ollama")

    def boom(model=None, base_url=None):
        raise NoOllama()

    import shesh_harness.evaluator as ev
    monkeypatch.setattr(ev, "make_ollama_responder", boom)
    out = server.refine_with_llm("test", "trajectory")
    assert set(out) == {"ok", "error"}
    assert out["ok"] is False
    assert "no ollama" in out["error"]
