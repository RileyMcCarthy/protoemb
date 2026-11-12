#!/usr/bin/env bash
# Generate the `thermostat` example in all three target languages and verify
# each one: C compiles (-Wall -Wextra), Rust passes its generated round-trip
# tests, TypeScript typechecks under --strict. Proves ProtoEmb is generic: no
# consumer-specific assumptions leak into the generator or runtime.
#
# Cross-language byte-identical wire is not checked here; that is
# tests/conformance (`make test-conformance`).
#
# Requires: python3 (+ pyyaml, jinja2), a C compiler, rustc, and npx (ships
# with node; it fetches a pinned TypeScript).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
core="$here/.."
schema="$here/thermostat.yaml"
templates="$core/core/templates"
gen="$core/core/generate.py"
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT

echo "== generating thermostat into $out =="
for t in c rs ts; do
  python3 "$gen" --schema "$schema" --target "$t" --output "$out/$t" --templates "$templates"
done

echo "== C: compile generated codec =="
cc -std=c11 -Wall -Wextra -c "$out/c/thermostat.c" -o "$out/c/thermostat.o" -I "$out/c"
echo "   ok"

echo "== Rust: rustc --test (built-in round-trip + facade tests) =="
rustc --edition 2021 --test "$out/rs/thermostat.rs" -o "$out/rs/test_bin"
"$out/rs/test_bin"

echo "== TypeScript: tsc --noEmit typecheck =="
# Pin TypeScript to the last 5.x line via npx: TS 6.0 removed the `node10`
# moduleResolution this leg uses, so an unpinned global `tsc` breaks whenever the
# host has 6.x. Always go through npx so the compiler is deterministic; the
# `--ignoreDeprecations 5.0` flags below silence node10's 5.x deprecation.
tsc_bin() { npx --yes -p typescript@5.9 tsc "$@"; }
tsc_flags=(--noEmit --strict --skipLibCheck --target es2020 --lib es2020,dom --ignoreDeprecations 5.0)
tsc_bin "${tsc_flags[@]}" "$out/ts/thermostat.ts"
echo "   ok"

echo ""
echo "ALL TARGETS OK — ProtoEmb generated a C/Rust/TS codec that compiles,"
echo "typechecks and round-trips for an independent protocol (custom prefix,"
echo "multiple nodes, remap enum, nested structs, arrays, optional fields, tagged"
echo "unions, packed + aligned). Byte-identical wire across the three targets is"
echo "checked by tests/conformance (make test-conformance)."
