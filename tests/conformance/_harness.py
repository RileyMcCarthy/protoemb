"""Cross-language conformance plumbing: generate a schema to C/Rust/TS, compile a
small driver against each generated codec, run it, and return its stdout lines.

A *driver* is a tiny program that, for each test vector, encodes the value,
re-encodes the decode of those bytes (a round-trip self-check), and prints one
`label hex` line. Byte-identical stdout across languages == wire conformance.

Toolchains are probed lazily; a missing compiler yields `None` so callers can
`pytest.skip` rather than fail on a machine that lacks (say) a Rust toolchain.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

CORE_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "core"))
GENERATE_PY = os.path.join(CORE_DIR, "generate.py")
TEMPLATES_DIR = os.path.join(CORE_DIR, "templates")


def have(tool):
    return shutil.which(tool) is not None


def have_tsc():
    # The TS leg runs via `npx` (pinned TypeScript), which ships with node.
    return have("npx")


def generate_codec(schema_path, prefix, target, out_dir):
    """Generate one target's codec into out_dir; raise on generator error."""
    os.makedirs(out_dir, exist_ok=True)
    cmd = [
        sys.executable, GENERATE_PY,
        "--schema", str(schema_path), "--target", target,
        "--output", str(out_dir), "--templates", TEMPLATES_DIR,
        "--prefix", prefix,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"generate {target} failed:\n{r.stderr}")


def _run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError(
            f"command failed ({' '.join(map(str, cmd))}):\n{r.stdout}\n{r.stderr}"
        )
    return r.stdout


# ── Per-language build + run ─────────────────────────────────────────────────

def build_run_c(work_dir, prefix_lower, driver_src):
    """Compile `driver_src` against the generated C codec and run it."""
    if not have("cc"):
        return None
    src = os.path.join(work_dir, "driver.c")
    with open(src, "w") as f:
        f.write(driver_src)
    exe = os.path.join(work_dir, "driver_c")
    # -Wall (no -Werror): the generated header carries `static const` remap tables
    # that a driver may legitimately not reference (matches examples/verify.sh).
    _run(["cc", "-std=c11", "-Wall", "-I", work_dir,
          os.path.join(work_dir, f"{prefix_lower}.c"), src, "-o", exe])
    return _run([exe]).splitlines()


def build_run_rust(work_dir, prefix_lower, driver_src):
    """Compile `driver_src` (which `#[path]`-includes the codec) and run it."""
    if not have("rustc"):
        return None
    src = os.path.join(work_dir, "driver.rs")
    with open(src, "w") as f:
        f.write(driver_src)
    exe = os.path.join(work_dir, "driver_rs")
    _run(["rustc", "--edition", "2021", "-A", "warnings", src, "-o", exe])
    return _run([exe]).splitlines()


def build_run_ts(work_dir, prefix_lower, driver_src):
    """Typecheck+transpile `driver_src` against the generated TS codec, run on node."""
    if not have_tsc() or not have("node"):
        return None
    src = os.path.join(work_dir, "driver.ts")
    with open(src, "w") as f:
        f.write(driver_src)
    js_dir = os.path.join(work_dir, "js")
    # Pin TypeScript to the last 5.x line: TS 6.0 removed `moduleResolution node`
    # (node10), so an unpinned global `tsc` breaks this leg whenever a runner
    # pulls 6.x. npx fetches the pinned compiler regardless of what's installed
    # globally, and `--ignoreDeprecations 5.0` silences node10's 5.x deprecation.
    tsc = ["npx", "--yes", "-p", "typescript@5.9", "tsc"]
    _run(tsc + [
        "--target", "es2020", "--module", "commonjs", "--moduleResolution", "node",
        "--strict", "--skipLibCheck", "--ignoreDeprecations", "5.0",
        "--outDir", js_dir, src,
    ])
    return _run(["node", os.path.join(js_dir, "driver.js")]).splitlines()


BUILDERS = {"c": build_run_c, "rs": build_run_rust, "ts": build_run_ts}


# ── High-level orchestration shared by every conformance test module ─────────

def run_all(schema_path, prefix, vectors, work_dir):
    """Generate `schema` to all targets, build+run each available driver over
    `vectors`, and return {lang: [lines]} for the toolchains that exist."""
    import generate as gen
    from render import Renderer  # local import: render imports `generate`
    renderer = Renderer(gen.load_yaml(schema_path), prefix)
    for target in ("c", "rs", "ts"):
        generate_codec(schema_path, prefix, target, work_dir)
    out = {}
    for lang, builder in BUILDERS.items():
        lines = builder(work_dir, prefix.lower(), renderer.driver(lang, vectors))
        if lines is not None:
            out[lang] = lines
    return out


def pivot_by_label(outputs):
    """Map {lang: ['label hex', ...]} -> {label: {lang: hex}}."""
    by_label = {}
    for lang, lines in outputs.items():
        for ln in lines:
            label, hexstr = ln.split(" ", 1)
            by_label.setdefault(label, {})[lang] = hexstr
    return by_label


# Languages the CI conformance gate expects when hard-require is on.
REQUIRED_LANGS = frozenset({"c", "rs", "ts"})
GOLDENS_DIR = os.path.join(os.path.dirname(__file__), "goldens")


def require_all_langs_enabled():
    """True when CI (or a local full gate) demands C + Rust + TypeScript."""
    return os.environ.get("PROTOEMB_CONFORMANCE_REQUIRE_ALL", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def assert_language_coverage(outputs, *, min_langs=2):
    """Assert enough toolchains ran for a meaningful conformance check.

    Locally, a missing compiler still soft-skips that language (see builders).
    On CI, set ``PROTOEMB_CONFORMANCE_REQUIRE_ALL=1`` so a missing or empty
    TypeScript (or C/Rust) leg fails hard instead of greenwashing on C+RS alone.
    """
    got = set(outputs)
    if require_all_langs_enabled():
        missing = REQUIRED_LANGS - got
        assert not missing, (
            f"PROTOEMB_CONFORMANCE_REQUIRE_ALL is set: need languages "
            f"{sorted(REQUIRED_LANGS)}, missing {sorted(missing)} "
            f"(ran: {sorted(got)})"
        )
        for lang in sorted(REQUIRED_LANGS):
            assert outputs[lang], f"{lang} produced empty stdout"
    else:
        assert len(got) >= min_langs, (
            f"need >={min_langs} toolchains for conformance, ran: {sorted(got)}"
        )


def agreed_wire_by_label(outputs):
    """Return {label: hex} only for labels where every language agrees.

    Labels that diverge across languages are omitted (callers should already
    fail the multi-lang assert separately).
    """
    agreed = {}
    for label, per_lang in pivot_by_label(outputs).items():
        values = set(per_lang.values())
        if len(values) == 1:
            agreed[label] = next(iter(values))
    return agreed


def assert_matches_goldens(outputs, suite_name):
    """Lock agreed multi-lang wire hex against tests/conformance/goldens/<suite>.json.

    Only labels present in the golden file are checked. Update goldens with::

        PROTOEMB_UPDATE_GOLDENS=1 pytest tests/conformance/...
    """
    import json

    path = os.path.join(GOLDENS_DIR, f"{suite_name}.json")
    agreed = agreed_wire_by_label(outputs)
    update = os.environ.get("PROTOEMB_UPDATE_GOLDENS", "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    if update:
        os.makedirs(GOLDENS_DIR, exist_ok=True)
        # Merge: keep prior keys unless this run re-emits them with agreement.
        prior = {}
        if os.path.exists(path):
            with open(path) as f:
                prior = json.load(f)
        prior.update(agreed)
        with open(path, "w") as f:
            json.dump(dict(sorted(prior.items())), f, indent=2)
            f.write("\n")
        return

    assert os.path.exists(path), (
        f"missing golden file {path}; generate with PROTOEMB_UPDATE_GOLDENS=1"
    )
    with open(path) as f:
        expected = json.load(f)
    mismatches = []
    for label, want in sorted(expected.items()):
        got = agreed.get(label)
        if got is None:
            mismatches.append(f"{label}: no multi-lang agreement (or missing from run)")
        elif got != want:
            mismatches.append(f"{label}: golden={want} got={got}")
    assert not mismatches, "golden wire mismatch:\n" + "\n".join(mismatches)
