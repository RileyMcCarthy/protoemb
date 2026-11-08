"""The generated C runtime's NACK frames, byte for byte.

Generates a small protocol, compiles its C runtime against handlers written
here, feeds it request frames, and checks the reply on the wire: every NACK is
[0x55][0x00][CMD][REASON], with the runtime's own reasons for what it rejects
itself and the handler's reason for what the handler refuses.
"""

import shutil
import subprocess

import pytest
import yaml
from protoemb_testkit import field, generate, message, schema, struct

CC = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
pytestmark = pytest.mark.skipif(CC is None, reason="no C compiler on PATH")

SCHEMA = schema(
    prefix="Nk",
    structs={
        "Level": struct(field("value", "uint8")),
        "Notification": struct(field("code", "uint8")),
    },
    messages={
        "status": message(tx_node="dev", command_id=1, response="Level"),
        "set_level": message(tx_node="host", command_id=2, request="Level"),
        "enable": message(tx_node="host", command_id=3, request="bool"),
    },
    nack_reasons=[
        {"name": "TOO_HIGH", "description": "The level is above the limit."},
        {"name": "LOCKED", "value": 0x40, "description": "The device is locked."},
    ],
)

HARNESS = r"""
#include <stdio.h>
#include <string.h>
#include "nk_runtime.h"

static uint8_t tx[64];
static uint16_t txLen;

bool Nk_sendBytes(const uint8_t *data, uint16_t size)
{
    memcpy(&tx[txLen], data, size);
    txLen = (uint16_t)(txLen + size);
    return true;
}
uint32_t Nk_getTimeMs(void) { return 0U; }
bool Nk_fill_notification(Nk_Notification_t *out) { (void)out; return false; }

bool Nk_onRead_status(Nk_Level_t *out) { (void)out; return false; }

Nk_RuntimeWriteDisposition_E Nk_onWrite_set_level(const Nk_Level_t *in)
{
    if (in->value == 0U) { return NK_RUNTIME_WRITE_DISPOSITION_NACK; }
    if (in->value == 7U) { return NK_RUNTIME_WRITE_DISPOSITION_NACK_LOCKED; }
    return (in->value > 100U) ? NK_RUNTIME_WRITE_DISPOSITION_NACK_TOO_HIGH : NK_RUNTIME_WRITE_DISPOSITION_ACK;
}
Nk_RuntimeWriteDisposition_E Nk_onWriteRaw_set_level(const uint8_t *payload, uint16_t payloadSize)
{
    (void)payload; (void)payloadSize;
    return NK_RUNTIME_WRITE_DISPOSITION_NACK_BAD_SIZE;
}
Nk_RuntimeWriteDisposition_E Nk_onWrite_enable(bool in) { (void)in; return NK_RUNTIME_WRITE_DISPOSITION_ACK; }

int main(int argc, char **argv)
{
    Nk_Runtime_t rt;
    Nk_Runtime_init(&rt);
    for (int i = 1; i < argc; i++)
    {
        Nk_Runtime_feedByte(&rt, (uint8_t)strtoul(argv[i], NULL, 16));
    }
    for (uint16_t i = 0U; i < txLen; i++)
    {
        printf("%02x%s", tx[i], (i + 1U < txLen) ? " " : "\n");
    }
    return 0;
}
"""


def crc8(data):
    crc = 0
    for b in data:
        for _ in range(8):
            mix = (crc ^ b) & 1
            crc >>= 1
            if mix:
                crc ^= 0x8C
            b >>= 1
    return crc


def write_frame(command, payload):
    n = len(payload)
    return [0x55, 0x01, command, n & 0xFF, n >> 8, *payload, crc8(payload)]


@pytest.fixture(scope="module")
def device(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("nack")
    schema_path = tmp / "nk.yaml"
    schema_path.write_text(yaml.safe_dump(SCHEMA))
    out = tmp / "c"
    r = generate(schema_path, "c", out)
    assert r.returncode == 0, r.stderr
    (out / "harness.c").write_text(HARNESS.replace("#include <stdio.h>", "#include <stdio.h>\n#include <stdlib.h>"))
    exe = tmp / "nk"
    cc = subprocess.run(
        [CC, "-std=c11", "-I", str(out), str(out / "harness.c"),
         str(out / "nk_runtime.c"), str(out / "nk.c"), "-o", str(exe)],
        capture_output=True, text=True,
    )
    assert cc.returncode == 0, cc.stderr

    def send(frame):
        run = subprocess.run([str(exe), *[f"{b:02x}" for b in frame]], capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        return run.stdout.strip()

    return send


def test_handler_reason_is_sent(device):
    assert device(write_frame(2, [150])) == "55 00 02 20"


def test_handler_reason_with_explicit_value(device):
    assert device(write_frame(2, [7])) == "55 00 02 40"


def test_plain_nack_is_refused(device):
    assert device(write_frame(2, [0])) == "55 00 02 00"


def test_ack_is_three_bytes(device):
    assert device(write_frame(2, [50])) == "55 01 02"


def test_unknown_write_command(device):
    assert device(write_frame(9, [1])) == "55 00 09 01"


def test_unknown_read_command(device):
    assert device([0x55, 0x00, 0x09]) == "55 00 09 01"


def test_bad_crc(device):
    frame = write_frame(2, [50])
    frame[-1] ^= 0xFF
    assert device(frame) == "55 00 02 02"


def test_wrong_size_bool_payload(device):
    assert device(write_frame(3, [])) == "55 00 03 03"


def test_wrong_size_struct_payload_reaches_raw_handler(device):
    assert device(write_frame(2, [1, 2])) == "55 00 02 03"


def test_read_with_nothing_to_answer(device):
    assert device([0x55, 0x00, 0x01]) == "55 00 01 04"
