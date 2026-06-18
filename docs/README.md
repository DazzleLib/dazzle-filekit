# dazzle-filekit documentation

This directory holds the full reference and integration documentation for
`dazzle-filekit`. The repo root keeps a slim [`README.md`](../README.md)
focused on the Quick Start; detailed content lives here.

For consumer-facing upgrade notes, see [`BREAKING_CHANGES.md`](../BREAKING_CHANGES.md)
and [`CHANGELOG.md`](../CHANGELOG.md) at the repo root. Those stay front-
and-center so anyone browsing the root can see them before bumping a pin.

---

## Reference

- **[api-reference.md](api-reference.md)** — full function-by-function
  reference. Every public symbol in `dazzle_filekit`, organized by
  subsystem (paths, file operations, metadata, platform-specific, disk
  space, verification, utilities, validation, logging).
- **[api-stability.md](api-stability.md)** — the *locked* public API
  surface and the external callers that depend on each symbol
  (claude-session-logger, dazzlecmd safedel/fixpath/links, github-
  traffic-tracker, preservelib, README examples). Changes to symbols
  in the locked tables require a migration plan per the top of the
  document. `tests/test_import_stability.py` is the automated canary
  that enforces this contract.
- **[platform-support.md](platform-support.md)** — platform matrix
  (Windows / Linux / WSL / macOS), test counts, and platform-specific
  feature breakdown. Includes the cross-platform path conversion
  table with all the edge cases filekit handles.

## Integration guides

- **[preservelib-integration.md](preservelib-integration.md)** — how
  [preservelib](https://github.com/DazzleTools/preserve) composes with
  filekit. Defines the layering contract: filekit is primitives,
  preservelib is workflow, dependency direction is one-way
  (`preservelib → filekit`).
- **[unctools-integration.md](unctools-integration.md)** — how
  filekit (L1) and [UNCtools](https://github.com/DazzleLib/UNCtools)
  (L0) compose. filekit has native UNC *detection* (`is_unc_path`,
  `classify_fs_object`) and delegates UNC identity to UNCtools, a **hard
  dependency as of 0.3.0**. Covers the `try_path_variants=` resolver
  edge and explicit UNC ↔ drive-letter *translation* patterns.

## Planning / roadmap

The v0.3.0 "seamless file operations" roadmap lives in GitHub issues,
not in this directory. See the
[**Roadmap epic #5**](https://github.com/DazzleLib/dazzle-filekit/issues/5)
for the vision ("file management should feel like data management"),
architecture diagram, acceptance criteria, and sub-issue breakdown.
