"""Skill marketplace primitives — export/import skills as shareable files.

A skill is `name -> markdown body` in harness state. This module gives the
minimal honest marketplace: export a skill (or all skills) to a single
portable JSON file, and import such a file back. The exported file is the
shareable unit — copy it to another machine, a git repo, or a hosted
directory (the full open-space.cloud-style hosted marketplace stays a
roadmap Future item; the format is the primitive it would build on).

Design rules:
- export never touches state (pure read).
- import is additive and non-destructive by default: existing skills are
  kept, duplicates are reported, and `overwrite=False` refuses to clobber
  (caller decides).
- malformed/unknown entries are reported, never silently dropped.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

FORMAT_VERSION = 1
MANIFEST_KEYS = {"format", "exported_at", "skills"}


class SkillsFileError(ValueError):
    """Raised when a file is not a valid skills export."""


@dataclass
class ImportResult:
    imported: list[str]
    skipped_existing: list[str]
    skipped_malformed: list[str]


def export_skills(skills: dict[str, str], out_path: Path) -> Path:
    """Write {format, exported_at, skills} to out_path. Returns out_path."""
    payload = {
        "format": FORMAT_VERSION,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "skills": dict(skills),
    }
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out_path


def load_skills_file(path: Path) -> dict[str, str]:
    """Read a skills file; raise SkillsFileError on malformed structure."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SkillsFileError(f"{path}: not a JSON object")  # noqa: TRY003 — path is essential debug context
    if not MANIFEST_KEYS.issubset(raw):
        missing = MANIFEST_KEYS - set(raw)
        raise SkillsFileError(f"{path}: missing keys {sorted(missing)}")  # noqa: TRY003 — path is essential debug context
    skills = raw.get("skills")
    if not isinstance(skills, dict):
        raise SkillsFileError(f"{path}: 'skills' must be an object")  # noqa: TRY003 — path is essential debug context
    for name, body in skills.items():
        if not isinstance(name, str) or not isinstance(body, str):
            raise SkillsFileError(f"{path}: skill {name!r} must map to a string body")  # noqa: TRY003 — path is essential debug context
    return skills


def import_skills(
    current: dict[str, str],
    path: Path,
    *,
    overwrite: bool = False,
) -> ImportResult:
    """Merge skills from a file into `current`.

    Returns the result object; `current` is mutated only for imported
    entries. Non-destructive by default: existing names are skipped unless
    overwrite=True. Malformed input is reported, never silently dropped.
    """
    try:
        incoming = load_skills_file(path)
    except (OSError, SkillsFileError, json.JSONDecodeError) as e:
        return ImportResult([], [], [str(e)])

    result = ImportResult([], [], [])
    for name, body in incoming.items():
        if name in current and not overwrite:
            result.skipped_existing.append(name)
            continue
        if not name or not body:
            result.skipped_malformed.append(name)
            continue
        current[name] = body
        result.imported.append(name)
    return result
