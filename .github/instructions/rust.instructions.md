---
applyTo: "framing/**,runtime/**"
---

Rust (`protoemb-framing` + `protoemb-runtime`).

- `framing` stays **zero-dependency** (`no_std`-friendly wire parsing).
- `runtime`'s native/wasm split is cfg-gated: `serialport`/`libc` are
  native-only, `wasm-bindgen` & co. wasm-only — never leak one side into the
  other. The wasm CI job must keep building.
- The crates are deliberately **workspace-free path crates**: do not add a
  workspace root. Consumers depend on each crate by path and build `runtime/`
  on its own with `wasm-pack`; CI, cargo-deny and the MSRV job all run per
  manifest.
- Wire-format changes must update `docs/wire-format.md` and the conformance
  vectors in the same change.

Don't re-report Clippy or build errors.
