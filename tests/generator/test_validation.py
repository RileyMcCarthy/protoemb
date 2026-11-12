"""validate_schema error paths. Each builds a minimal schema that trips exactly
one rule and asserts the diagnostic reaches stderr before SystemExit."""

import pytest
from protoemb_testkit import (
    enum,
    field,
    message,
    schema,
    struct,
    union,
    validate,
)

# A trivial payload struct for messages that need a request/response type.
PAYLOAD = {"P": struct(field("x", "uint8"))}


def expect_error(capsys, s, substring, **kw):
    with pytest.raises(SystemExit):
        validate(s, **kw)
    err = capsys.readouterr().err
    assert substring in err, f"expected {substring!r} in stderr, got:\n{err}"


# ── Unions ───────────────────────────────────────────────────────────────────

def test_union_empty_variants(capsys):
    expect_error(capsys, schema(unions={"U": union()}), "at least one variant")


def test_union_duplicate_variant_name(capsys):
    u = union({"name": "a", "type": "uint8"}, {"name": "a", "type": "int16"})
    expect_error(capsys, schema(unions={"U": u}), "duplicate variant name")


def test_union_string_variant(capsys):
    u = union({"name": "s", "type": "string"})
    expect_error(capsys, schema(unions={"U": u}), "string variants are not supported")


def test_union_nested_union(capsys):
    inner = union({"name": "a", "type": "uint8"})
    outer = union({"name": "b", "type": "Inner"})
    expect_error(capsys, schema(unions={"Inner": inner, "Outer": outer}),
                 "nested unions are not supported")


def test_union_struct_variant(capsys):
    u = union({"name": "r", "type": "Reading"})
    s = schema(structs={"Reading": struct(field("x", "uint8"))}, unions={"U": u})
    expect_error(capsys, s, "struct variants are not yet supported")


def test_union_unknown_type(capsys):
    u = union({"name": "x", "type": "frobnicate"})
    expect_error(capsys, schema(unions={"U": u}), "references unknown type")


def test_union_64bit_variant(capsys):
    u = union({"name": "x", "type": "uint64"})
    expect_error(capsys, schema(unions={"U": u}), "64-bit integers are not supported")


def test_float_in_aligned_union(capsys):
    u = union({"name": "g", "type": "float"}, encoding="aligned")
    expect_error(capsys, schema(unions={"U": u}),
                 "'float' is not supported in an aligned union")


# ── Layout defaults ──────────────────────────────────────────────────────────

def test_default_byte_and_bit_order_are_accepted():
    s = schema(structs=PAYLOAD,
               defaults={"byte_order": "little_endian", "bit_order": "lsb_first"})
    validate(s)


@pytest.mark.parametrize("key,value", [
    ("byte_order", "big_endian"),
    ("bit_order", "msb_first"),
])
def test_unsupported_order_is_rejected(key, value):
    with pytest.raises(SystemExit, match=f"defaults.{key}.*is not supported"):
        validate(schema(structs=PAYLOAD, defaults={key: value}))


# ── Struct fields ────────────────────────────────────────────────────────────

def test_field_unknown_type(capsys):
    s = schema(structs={"S": struct(field("x", "wibble"))})
    expect_error(capsys, s, "S.x: references unknown type 'wibble'")


@pytest.mark.parametrize("ftype", ["int64", "uint64"])
def test_field_64bit_integer(capsys, ftype):
    s = schema(structs={"S": struct(field("big", ftype))})
    expect_error(capsys, s, "S.big: 64-bit integers are not supported")


def test_float_in_aligned_struct(capsys):
    s = schema(structs={"S": struct(field("f", "float"), encoding="aligned")})
    expect_error(capsys, s, "'float' is not supported in an aligned struct")


def test_float_in_packed_struct_is_accepted():
    s = schema(structs={"S": struct(field("f", "float", min=0, max=10, scale=10))})
    validate(s)


def test_duplicate_field_name(capsys):
    s = struct(field("x", "uint8"), field("x", "int16"))
    expect_error(capsys, schema(structs={"S": s}), "duplicate field name")


def test_min_below_type_range(capsys):
    s = struct(field("x", "int8", min=-200, max=0))
    expect_error(capsys, schema(structs={"S": s}), "below int8 minimum")


def test_max_above_type_range(capsys):
    s = struct(field("x", "uint8", min=0, max=300))
    expect_error(capsys, schema(structs={"S": s}), "above uint8 maximum")


def test_array_count_not_positive(capsys):
    s = struct(field("x", "uint8", count=0))
    expect_error(capsys, schema(structs={"S": s}), "count must be a positive integer")


def test_string_array_rejected(capsys):
    s = struct(field("x", "string", count=3), encoding="aligned")
    expect_error(capsys, schema(structs={"S": s}), "string arrays are not supported")


def test_optional_array_rejected(capsys):
    s = struct(field("x", "uint8", count=3, optional=True))
    expect_error(capsys, schema(structs={"S": s}), "cannot be both optional and an array")


def test_optional_string_rejected(capsys):
    s = struct(field("x", "string", optional=True), encoding="aligned")
    expect_error(capsys, schema(structs={"S": s}), "optional strings are not supported")


def test_fractional_scale_on_int_rejected(capsys):
    s = struct(field("x", "int16", scale=0.5))
    expect_error(capsys, schema(structs={"S": s}), "requires a 'float' field type")


def test_fractional_scale_on_float_ok():
    s = struct(field("x", "float", scale=0.5))
    validate(schema(structs={"S": s}))  # must not raise


def test_packed_range_exceeds_explicit_bits(capsys):
    s = struct(field("x", "uint16", min=0, max=1000, bits=5))
    expect_error(capsys, schema(structs={"S": s}), "only 5 allocated")


# ── Messages ─────────────────────────────────────────────────────────────────

def msg_schema(messages, **kw):
    return schema(structs=PAYLOAD, messages=messages, **kw)


def test_tx_node_must_be_nonempty(capsys):
    s = msg_schema({"m": message(tx_node="", command_id=0, response="P")})
    expect_error(capsys, s, "must be a non-empty string")


def test_tx_node_not_in_nodes(capsys):
    s = msg_schema({"m": message(tx_node="ghost", command_id=0, response="P")},
                   nodes=["dev"])
    expect_error(capsys, s, "is not in configured nodes")


def test_nodes_must_be_list(capsys):
    s = msg_schema({"m": message(command_id=0, response="P")}, nodes="dev")
    expect_error(capsys, s, "must be a list of strings")


def test_command_id_omitted_requires_response(capsys):
    s = msg_schema({"m": message(request="P")})
    expect_error(capsys, s, "requires response when command_id is omitted")


def test_periodic_requires_command_id(capsys):
    s = msg_schema({"m": message(period_ms=1000, response="P")})
    expect_error(capsys, s, "periodic message requires command_id")


def test_period_ms_must_be_integer(capsys):
    s = msg_schema({"m": message(command_id=0, period_ms=1.5, response="P")})
    expect_error(capsys, s, "period_ms: must be an integer")


def test_period_ms_must_be_positive(capsys):
    s = msg_schema({"m": message(command_id=0, period_ms=0, response="P")})
    expect_error(capsys, s, "period_ms: must be > 0")


def test_request_unknown_struct(capsys):
    s = msg_schema({"m": message(command_id=0, request="Nope")})
    expect_error(capsys, s, "request: references unknown struct")


def test_response_unknown_struct(capsys):
    s = msg_schema({"m": message(command_id=0, response="Nope")})
    expect_error(capsys, s, "response: references unknown struct")


def test_invalid_command_frame(capsys):
    s = msg_schema({"m": message(command_id=0, response="P", command_frame="sideways")})
    expect_error(capsys, s, "command_frame: must be 'read' or 'write'")


def test_invalid_priority(capsys):
    s = msg_schema({"m": message(command_id=0, response="P", priority="urgent")})
    expect_error(capsys, s, "priority: must be 'high' or 'low'")


def test_duplicate_read_command_id(capsys):
    s = msg_schema({
        "a": message(command_id=0, response="P", command_frame="read"),
        "b": message(command_id=0, request="none", response="P"),  # also read frame
    })
    expect_error(capsys, s, "duplicate READ command_id")


def test_duplicate_write_command_id(capsys):
    s = msg_schema({
        "a": message(command_id=0, request="P"),
        "b": message(command_id=0, request="bool"),
    })
    expect_error(capsys, s, "duplicate WRITE command_id")


def test_data_command_id_collision_across_frames(capsys):
    # A READ response and a WRITE-frame query sharing a command id: distinct
    # frame spaces, but the typed facade can't tell their DATA frames apart.
    s = msg_schema({
        "rd": message(command_id=3, response="P"),
        "wr": message(command_id=3, request="P", response="P", command_frame="write"),
    })
    expect_error(capsys, s, "DATA command_id 3 collides")


# ── Happy path ───────────────────────────────────────────────────────────────

def test_valid_schema_passes(capsys):
    s = schema(
        prefix="Demo",
        nodes=["dev", "host"],
        enums={"Mode": enum("OFF", "ON")},
        structs={"P": struct(field("m", "Mode"), field("x", "uint8", min=0, max=100))},
        messages={
            "telemetry": message(tx_node="dev", command_id=0, period_ms=500, response="P"),
            "set": message(tx_node="host", command_id=0, request="P"),
        },
    )
    validate(s)  # must not raise
    out = capsys.readouterr().out
    assert "Schema validation passed" in out


# ── NACK reasons ─────────────────────────────────────────────────────────────

def test_nack_reason_clashes_with_runtime_name(capsys):
    s = schema(nack_reasons=[{"name": "BAD_CRC", "description": "x"}])
    expect_error(capsys, s, "duplicate name")


def test_nack_reason_value_in_runtime_range(capsys):
    s = schema(nack_reasons=[{"name": "MINE", "value": 0x05, "description": "x"}])
    expect_error(capsys, s, "value must be an integer in [0x20, 0xFF]")


def test_nack_reason_duplicate_value(capsys):
    s = schema(nack_reasons=[
        {"name": "ONE", "value": 0x30, "description": "x"},
        {"name": "TWO", "value": 0x30, "description": "y"},
    ])
    expect_error(capsys, s, "already used by ONE")


def test_nack_reason_name_case(capsys):
    s = schema(nack_reasons=[{"name": "busy", "description": "x"}])
    expect_error(capsys, s, "UPPER_SNAKE_CASE")


def test_nack_reason_description_quote(capsys):
    s = schema(nack_reasons=[{"name": "BUSY", "description": 'say "hi"'}])
    expect_error(capsys, s, "description must be one line")


def test_nack_reason_description_closes_c_comment(capsys):
    s = schema(nack_reasons=[{"name": "BUSY", "description": "Busy */ oops"}])
    expect_error(capsys, s, "or '*/'")


def test_nack_reason_duplicate_schema_names_omit_runtime_hint(capsys):
    s = schema(nack_reasons=[
        {"name": "BUSY", "description": "x"},
        {"name": "BUSY", "description": "y"},
    ])
    with pytest.raises(SystemExit):
        validate(s)
    err = capsys.readouterr().err
    assert "nack_reasons.BUSY: duplicate name" in err
    assert "the runtime defines" not in err
