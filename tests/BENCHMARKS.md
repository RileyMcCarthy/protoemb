# Suite timing baselines

Record wall times from a clean CI-like run so multi-schema expansion stays
under budget. Update when adding conformance schemas.

| Command | Machine | Wall time | Notes |
|---|---|---|---|
| `PROTOEMB_CONFORMANCE_REQUIRE_ALL=1 python -m pytest tests -q` | local (dev) | ~10 s | 162 tests (2026-07-18) |
| `cargo test --manifest-path framing/Cargo.toml` | local | ~0.05 s | |
| `cargo test --manifest-path runtime/Cargo.toml` | local | &lt;1 s | after warm cache |

**Budget targets (design):** full `make test-ci` &lt; 5 min on ubuntu-latest;
conformance smoke preferred &lt; 3 min. Prefer one matrix schema over many
compile units when adding pairwise coverage.

To refresh after a change:

```bash
/usr/bin/time -p make test-ci
```
