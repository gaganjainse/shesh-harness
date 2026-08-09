"""sesha-harness: Continual Harness for safe self-improvement.

The immutable base system prompt is never modified. This component manages
supplemental state the agent can CRUD through evidence-backed refinements:

- supplemental prompt notes
- memories
- reusable skills (Markdown)
- subagent specifications

Every refinement is append-only with trigger/outcome, can be rolled back by ID,
and is only promoted to canary after the eval harness passes. This implements
the Prime Agent /refine pattern with the safety guardrails learned from the
"agent learns to cheat" failure mode: immutable policy, bounded autonomy, and
measured outcomes.
"""
from __future__ import annotations

__version__ = "0.1.0"
