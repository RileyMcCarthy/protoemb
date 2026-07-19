"""packed raw_storage: C and Rust must use min_wire (scaled integer) encode.

Policy (A2 for TypeScript): C/RS hold already-scaled wire integers (mN, µm);
TS stays physical-units API and applies scale on encode so wire still matches.
These unit tests lock the *generated* C and Rust formula shapes.
"""

from __future__ import annotations

import re

import pytest
from protoemb_testkit import field, generate, process, schema, struct

SCHEMA_YAML = """\
prefix: RawDemo
protocol_version: 1
structs:
  Sample:
    encoding: packed
    fields:
      - name: force
        type: int32
        scale: 1000
        raw_storage: true
        min: -100
        max: 100
      - name: position
        type: int32
        scale: 1000
        raw_storage: true
        min: -200
        max: 200
"""


@pytest.fixture(scope="module")
def schema_path(tmp_path_factory):
    p = tmp_path_factory.mktemp("raw") / "raw.yaml"
    p.write_text(SCHEMA_YAML)
    return p


def test_raw_storage_flag_on_processed_fields():
    s = schema(
        structs={
            "Sample": struct(
                field("force", "int32", scale=1000, raw_storage=True, min=-100, max=100),
                encoding="packed",
            )
        }
    )
    f = process(s)["structs"]["Sample"]["fields"][0]
    assert f["_raw_storage"] is True
    assert f["_min_wire"] == -100_000
    assert f["_max_wire"] == 100_000
    assert f["_scale"] == 1000


def test_generated_rust_packed_raw_uses_min_wire(schema_path, tmp_path):
    out = tmp_path / "rs"
    r = generate(schema_path, "rs", out)
    assert r.returncode == 0, r.stderr
    rs = (out / "rawdemo.rs").read_text()
    # Encode: (self.force - (-100000i32)) as u32 — no scale multiply on force
    assert re.search(
        r"self\.force\s*-\s*\(\s*-100000i32\s*\)",
        rs,
    ), "Rust encode must subtract min_wire"
    force_packs = re.findall(r"pack_bits\([^;]*self\.force[^;]*;", rs, re.DOTALL)
    assert force_packs, "expected pack_bits involving self.force"
    for pack in force_packs:
        assert "wrapping_mul" not in pack, f"raw force must not multiply scale:\n{pack}"
    # Decode restores min_wire
    assert re.search(
        r"as i32\)\s*\+\s*\(\s*-100000i32\s*\)",
        rs,
    ), "Rust decode must add min_wire back"


def test_generated_c_packed_raw_uses_min_wire(schema_path, tmp_path):
    out = tmp_path / "c"
    r = generate(schema_path, "c", out)
    assert r.returncode == 0, r.stderr
    c = (out / "rawdemo.c").read_text().replace(" ", "")
    assert "src->force-(-100000)" in c
    assert "+(-100000)" in c


def test_ts_still_applies_physical_scale_a2(schema_path, tmp_path):
    """A2: TypeScript keeps physical API — (value - min) * scale on encode."""
    out = tmp_path / "ts"
    r = generate(schema_path, "ts", out)
    assert r.returncode == 0, r.stderr
    ts = (out / "rawdemo.ts").read_text()
    assert re.search(
        r"Math\.round\(\(src\.force\s*-\s*\(-100\)\)\s*\*\s*1000\)",
        ts,
    ), "TS A2 must keep physical (value - min) * scale encode"
