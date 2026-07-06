# ProtoEmb

[![CI](https://github.com/RileyMcCarthy/protoemb/actions/workflows/ci.yml/badge.svg)](https://github.com/RileyMcCarthy/protoemb/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A small, dependency-light **binary protocol toolchain for embedded systems**.
Describe a protocol once in YAML; generate matching encode/decode code for
**C, TypeScript, and Rust**, plus a host-side serial runtime. The same wire
format is produced byte-for-byte by every target (enforced — see
[`examples/verify.sh`](examples/verify.sh)).

```text
schema.yaml ──► core/generate.py ──► C  (device firmware codec + runtime)
                (Jinja templates)     TypeScript (browser / Node)
                                      Rust (host / SIL)
            framing  ──► runtime ──► NDJSON bridge + WebAssembly client
            (wire format)  (Client / queue / transport)
```

## Layout

| Path | What |
|---|---|
| [`core/`](core/) | The code generator (`generate.py`) + Jinja `templates/` |
| [`framing/`](framing/) | `protoemb-framing` crate — wire frame parser/builder + CRC (zero dependencies) |
| [`runtime/`](runtime/) | `protoemb-runtime` crate — serial `Client`, priority queue, NDJSON `StdioBridge`, WASM `WasmClient` |
| [`examples/`](examples/) | An example `thermostat` protocol + `verify.sh` (generates & round-trips C/Rust/TS) |
| [`tests/`](tests/) | Self-contained suite — generator unit tests + cross-language wire conformance (`make test`) |
| [`docs/`](docs/) | [`wire-format.md`](docs/wire-format.md) — the frame + payload contract |

## Schema features

- **Enums** — plain, or `remap: true` for sparse semantic values (dense table or
  binary search, chosen automatically).
- **Structs** — `packed` (bit-level) or `aligned` (byte-level); per-field
  `scale`, `min`/`max` (offset-binary), explicit `bits:`, `raw_storage`.
- **Nested structs**, **fixed-count arrays** (`count: N`), **optional fields**
  (`optional: true`), and **tagged unions** (top-level `unions:`).
- **Messages** — `tx_node`, `command_id`, `period_ms`, `priority`,
  `request`/`response`; a generated typed facade (`decodeData` / `Inbound`).
- **Multi-node** — node-ID constants + opt-in source-addressed framing.

See [`docs/wire-format.md`](docs/wire-format.md) for the exact wire layout.

## Generate

```bash
python3 core/generate.py --schema my.yaml --target c  --output gen/c  --templates core/templates
python3 core/generate.py --schema my.yaml --target ts --output gen/ts --templates core/templates
python3 core/generate.py --schema my.yaml --target rs --output gen/rs --templates core/templates
# --prefix Name  overrides the library prefix (default: schema `prefix`, else ProtoEmb)
```

Generator deps: `pip install -r core/requirements.txt` (pyyaml, jinja2), or
`pip install ./core` (see [`core/pyproject.toml`](core/pyproject.toml)) for a
`protoemb-gen` CLI. Generation is deterministic: the same schema + templates
always produce byte-identical output (CI enforces this).

## Using ProtoEmb in your project

ProtoEmb is designed to be vendored as a **git submodule** and driven from your
build:

```bash
git submodule add https://github.com/RileyMcCarthy/protoemb.git vendor/protoemb
```

- **Device (C)** — run `generate.py --target c` as a pre-build hook (e.g. a
  PlatformIO `extra_scripts` hook) and compile the generated codec + runtime
  with your firmware.
- **Browser / Node (TypeScript)** — run `generate.py --target ts` from an npm
  script; for browser serial, build the runtime to WebAssembly:
  `wasm-pack build vendor/protoemb/runtime --target web` (the `WasmClient`
  feeds on Web Serial bytes).
- **Host (Rust)** — run `generate.py --target rs` (or wire up
  [`core/cargo_build.py`](core/cargo_build.py) from a `build.rs`) and depend on
  `protoemb-runtime` / `protoemb-framing` as path crates.
- **Desktop bridge** — `cargo build --bin protoemb-bridge` (in `runtime/`)
  builds the NDJSON stdin/stdout bridge for apps that keep protocol logic in a
  child process. `PROTOEMB_BRIDGE_RESPONSE_TIMEOUT_MS` overrides its
  request/response timeout.

The two Rust crates are deliberately workspace-free path crates
(`publish = false`); their `Cargo.toml`s carry crates.io-ready metadata so
publishing later is a one-line change. A complete reference consumer — firmware
C target, browser WASM target, and Rust SIL target generated from one schema —
is the [MaD tensile tester](https://github.com/RileyMcCarthy/MaD).

## Verify

```bash
./examples/verify.sh   # generate the example to C/Rust/TS, compile/typecheck,
                       # round-trip, and assert byte-identical wire across all three
```

## Test

`make test` runs the full self-contained suite (see [`tests/`](tests/)):

```bash
make setup            # one-time: pip install pyyaml, jinja2, pytest
make test             # generator unit tests + cross-language wire conformance + Rust crates
make test-generator   # pytest over core/generate.py
make test-conformance # C == Rust == TS wire conformance (vector-driven)
make test-rust        # framing + runtime cargo tests
```

Toolchain: `python3`, `cc`, `cargo`; the TypeScript conformance leg needs
`node` + `tsc` and skips gracefully when they're absent. See
[`tests/README.md`](tests/README.md) for layout and how to add vectors.

## License

MIT — see [LICENSE](LICENSE).
