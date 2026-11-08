"""The NACK reason table in the generated TypeScript and Rust codecs.

A schema's own reasons — one numbered automatically, one given an explicit
value — must reach both host languages with the codes the C runtime sends.
Each driver is compiled against its generated codec and prints `code name`
for every reason; the outputs must agree with each other and with the table.
"""

import pytest
import yaml
from _harness import build_run_rust, build_run_ts, generate_codec, require_all_langs_enabled

SCHEMA = {
    "protocol_version": 1,
    "structs": {"Level": {"encoding": "packed", "fields": [{"name": "value", "type": "uint8"}]}},
    "messages": {"set_level": {"tx_node": "host", "command_id": 1, "request": "Level"}},
    "nack_reasons": [
        {"name": "TOO_HIGH", "description": "The level is above the limit."},
        {"name": "LOCKED", "value": 0x40, "description": "The device is locked."},
    ],
}

EXPECTED = [
    "0x00 REFUSED",
    "0x01 UNKNOWN_COMMAND",
    "0x02 BAD_CRC",
    "0x03 BAD_SIZE",
    "0x04 UNAVAILABLE",
    "0x20 TOO_HIGH",
    "0x40 LOCKED",
]

RS_DRIVER = """
#[path = "nk.rs"] mod codec;
fn main() {
    for (code, name, _meaning) in codec::NACK_REASONS {
        println!("0x{:02x} {}", code, name);
    }
}
"""

TS_DRIVER = """
import { NACK_REASON, NACK_REASON_INFO } from './nk';
for (const [name, code] of Object.entries(NACK_REASON)) {
    const info = NACK_REASON_INFO[code];
    if (info.name !== name) throw new Error(`${name} -> ${info.name}`);
    console.log(`0x${code.toString(16).padStart(2, '0')} ${name}`);
}
const locked: number = NACK_REASON.LOCKED;
if (NACK_REASON_INFO[locked].description !== 'The device is locked.') throw new Error('description');
"""


@pytest.fixture(scope="module")
def outputs(tmp_path_factory):
    work = tmp_path_factory.mktemp("nack_reasons")
    schema_path = work / "nk.yaml"
    schema_path.write_text(yaml.safe_dump(SCHEMA))
    for target in ("rs", "ts"):
        generate_codec(schema_path, "Nk", target, str(work))
    out = {}
    rs = build_run_rust(str(work), "nk", RS_DRIVER)
    if rs is not None:
        out["rs"] = rs
    ts = build_run_ts(str(work), "nk", TS_DRIVER)
    if ts is not None:
        out["ts"] = ts
    return out


def test_host_languages_carry_the_reason_table(outputs):
    # Only the host languages have the table; C's is the runtime enum, covered
    # byte for byte by tests/generator/test_runtime_nack.py.
    if require_all_langs_enabled():
        assert set(outputs) == {"rs", "ts"}, f"ran: {sorted(outputs)}"
    elif not outputs:
        pytest.skip("neither rustc nor node/npx is available")
    for lang, lines in outputs.items():
        assert lines == EXPECTED, f"{lang}: {lines}"
