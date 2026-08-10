"""Durable harness state (CRUD surface for self-improvement)."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

DATA_DIR = Path.home() / ".local" / "share" / "sesha" / "harness"

IMMUTABLE_FILES = {"safety-governance.md", "base-prompt.md"}


@dataclass
class HarnessState:
    supplemental_prompt: str = ""
    skills: dict[str, str] = field(default_factory=dict)       # name -> markdown
    memories: list[str] = field(default_factory=list)
    subagents: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path) -> HarnessState:
        path = root / "state.json"
        if not path.exists():
            return cls()
        return cls(**json.loads(path.read_text(encoding="utf-8")))

    def save(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / "state.json").write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")


@dataclass
class Refinement:
    id: str
    ts: float
    trigger: str
    kind: str           # prompt | skill | memory | subagent
    target: str
    before: str
    after: str
    outcome: str = "proposed"   # proposed | applied | reverted | rejected
    score: float | None = None


class Harness:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or DATA_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self.state = HarnessState.load(self.root)
        self.refinements: list[Refinement] = self._load_refinements()

    def _ref_path(self) -> Path:
        return self.root / "refinements.jsonl"

    def _load_refinements(self) -> list[Refinement]:
        p = self._ref_path()
        if not p.exists():
            return []
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(Refinement(**json.loads(line)))
            except (json.JSONDecodeError, TypeError):
                continue
        return out

    def _append_refinement(self, r: Refinement) -> None:
        with self._ref_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
        self.refinements.append(r)

    # ── CRUD (the agent may call these, subject to Brain policy) ─────────
    def set_prompt(self, text: str, trigger: str) -> Refinement:
        return self._apply("prompt", "supplemental", self.state.supplemental_prompt, text, trigger)

    def upsert_skill(self, name: str, body: str, trigger: str) -> Refinement:
        before = self.state.skills.get(name, "")
        return self._apply("skill", name, before, body, trigger)

    def add_memory(self, memory: str, trigger: str = "manual") -> Refinement:
        before = "\n".join(self.state.memories)
        after = before + ("\n" if before else "") + memory
        return self._apply("memory", "list", before, after, trigger)

    def upsert_subagent(self, name: str, spec: dict, trigger: str) -> Refinement:
        before = json.dumps(self.state.subagents.get(name, {}), sort_keys=True)
        after = json.dumps(spec, sort_keys=True)
        return self._apply("subagent", name, before, after, trigger)

    def _apply(self, kind: str, target: str, before: str, after: str, trigger: str) -> Refinement:
        r = Refinement(
            id=f"ref-{uuid.uuid4().hex[:12]}",
            ts=time.time(), trigger=trigger, kind=kind, target=target,
            before=before, after=after, outcome="applied",
        )
        if kind == "prompt":
            self.state.supplemental_prompt = after
        elif kind == "skill":
            self.state.skills[target] = after
        elif kind == "memory":
            self.state.memories = [m for m in after.splitlines() if m.strip()]
        elif kind == "subagent":
            self.state.subagents[target] = json.loads(after)
        self.state.save(self.root)
        self._append_refinement(r)
        return r

    def revert(self, ref_id: str) -> Refinement | None:
        for r in reversed(self.refinements):
            if r.id != ref_id or r.outcome != "applied":
                continue
            if r.kind == "prompt":
                self.state.supplemental_prompt = r.before
            elif r.kind == "skill":
                if r.before:
                    self.state.skills[r.target] = r.before
                else:
                    self.state.skills.pop(r.target, None)
            elif r.kind == "memory":
                self.state.memories = [m for m in r.before.splitlines() if m.strip()]
            elif r.kind == "subagent":
                if r.before:
                    self.state.subagents[r.target] = json.loads(r.before)
                else:
                    self.state.subagents.pop(r.target, None)
            r.outcome = "reverted"
            self.state.save(self.root)
            self._write_refinements()
            return r
        return None

    def _write_refinements(self) -> None:
        with self._ref_path().open("w", encoding="utf-8") as f:
            for r in self.refinements:
                f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")

    def prompt_block(self) -> str:
        """Render the supplemental prompt + memories for context assembly."""
        parts = []
        if self.state.supplemental_prompt:
            parts.append(self.state.supplemental_prompt)
        if self.state.skills:
            parts.append("# Skills\n" + "\n".join(
                f"- {n}" for n in sorted(self.state.skills)))
        if self.state.memories:
            parts.append("# Memories\n" + "\n".join(f"- {m}" for m in self.state.memories))
        return "\n\n".join(parts)
