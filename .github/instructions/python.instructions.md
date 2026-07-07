---
applyTo: "core/**,tests/**"
---

Python (protocol code generator + test suite). Lint config: `ruff.toml` at the
repo root. Target Python 3.9 (`core/pyproject.toml`).

Focus on what ruff can't decide:
- the generator's error-handling model (accumulate errors, then report;
  `SystemExit` vs `ValueError` by cause);
- schema-enrichment conventions (`_`-prefixed computed keys, don't overwrite
  raw keys);
- Jinja template hygiene — no logic pushed into templates, use the configured
  `prefix` (not a hardcoded name), keep the DO-NOT-EDIT banner;
- generation must stay deterministic — CI regenerates twice and diffs
  byte-for-byte;
- conformance vectors are the wire-format source of truth: a codec change
  needs matching vector + `docs/wire-format.md` updates.

Don't re-report ruff findings.
