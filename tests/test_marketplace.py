"""Offline tests for the skill marketplace primitives."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shesh_harness.marketplace import (  # noqa: E402
    export_skills,
    import_skills,
    load_skills_file,
)


def test_export_roundtrip(tmp_path):
    skills = {"git-workflow": "# Git\ncommit early", "docs": "# Docs\nwrite"}
    out = tmp_path / "skills.json"
    export_skills(skills, out)
    assert out.exists()
    assert load_skills_file(out) == skills


def test_export_has_manifest(tmp_path):
    out = tmp_path / "skills.json"
    export_skills({"a": "b"}, out)
    raw = out.read_text()
    assert '"format": 1' in raw
    assert '"exported_at"' in raw


def test_import_adds_new_skills(tmp_path):
    src = tmp_path / "in.json"
    export_skills({"new-skill": "body"}, src)
    current = {"existing": "keep"}
    result = import_skills(current, src)
    assert result.imported == ["new-skill"]
    assert result.skipped_existing == []
    assert current["new-skill"] == "body"
    assert current["existing"] == "keep"


def test_import_skips_existing_without_overwrite(tmp_path):
    src = tmp_path / "in.json"
    export_skills({"same": "new body"}, src)
    current = {"same": "old body"}
    result = import_skills(current, src)
    assert result.imported == []
    assert result.skipped_existing == ["same"]
    assert current["same"] == "old body"


def test_import_overwrite_replaces(tmp_path):
    src = tmp_path / "in.json"
    export_skills({"same": "new body"}, src)
    current = {"same": "old body"}
    result = import_skills(current, src, overwrite=True)
    assert result.imported == ["same"]
    assert current["same"] == "new body"


def test_import_malformed_file_reported(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    result = import_skills({}, bad)
    assert result.imported == []
    assert result.skipped_malformed  # error string recorded
    assert result.skipped_existing == []


def test_import_wrong_structure_reported(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"skills": "not-a-dict"}')
    result = import_skills({}, bad)
    assert result.skipped_malformed
    assert result.imported == []


def test_empty_skill_skipped(tmp_path):
    src = tmp_path / "in.json"
    src.write_text('{"format": 1, "exported_at": "t", "skills": {"": "x", "ok": ""}}')
    result = import_skills({}, src)
    assert result.imported == []
    assert sorted(result.skipped_malformed) == ["", "ok"]
