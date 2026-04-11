"""Characterization tests for filekit v0.3.x consolidation.

These tests document the CURRENT behavior of both filekit's own functions
and downstream (safedel/preservelib) implementations BEFORE the v0.3.x
consolidation. They are the baseline against which the refactor is measured.

Plan: C:/Users/Extreme/.claude/plans/functional-herding-dolphin.md
Design: C:/code/dazzlecmd/github/projects/core/safedel/private/claude/2026-04-10__18-05-15__filekit-audit-and-consolidation.md

Rules:
- These tests DOCUMENT behavior, they don't assert correctness.
- Each test is labeled with which implementation it characterizes.
- Tests that demonstrate gaps are PASS now, FAIL after the refactor
  (at which point the assertion is updated or the test is deleted).
"""
