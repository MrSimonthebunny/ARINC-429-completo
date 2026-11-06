import json

import pytest

from arinc429.domain.models import EncodingType, Instrument
from arinc429.domain.word import generate_word


def make_instrument(
    encoding: EncodingType = EncodingType.BNR,
    config: dict | None = None,
    minimum: float = -100,
    maximum: float = 100,
) -> Instrument:
    return Instrument(
        id=1,
        name="Altímetro",
        minimum=minimum,
        maximum=maximum,
        label="1",
        encoding=encoding,
        resolution=0.5,
        unit="ft",
        sdi=2,
        ssm=1,
        encoding_config=json.dumps(config) if config is not None else None,
    )


def bnr_config(parity: str = "odd") -> dict:
    return {
        "label_base": "decimal",
        "label_bit_order": "normal",
        "parity": parity,
        "data": {
            "zero_value": 0,
            "representation": "twos_complement",
            "data_bit_positions": list(range(19)),
        },
    }


def test_instrument_accepts_inclusive_range_endpoints() -> None:
    instrument = make_instrument()

    instrument.validate_value(instrument.minimum)
    instrument.validate_value(instrument.maximum)


@pytest.mark.parametrize("value", [-100.01, 100.01])
def test_instrument_rejects_out_of_range_values(value: float) -> None:
    with pytest.raises(ValueError, match="entre"):
        make_instrument().validate_value(value)


def test_word_has_32_bits_big_endian_bytes_and_odd_parity() -> None:
    word = generate_word(make_instrument(config=bnr_config()), 1)

    assert len(word.binary) == 32
    assert len(word.bytes_big_endian) == 4
    assert word.value >> 24 == 1
    assert (word.value >> 22) & 0b11 == 2
    assert (word.value >> 3) & ((1 << 19) - 1) == 2
    assert (word.value >> 1) & 0b11 == 1
    assert word.value.bit_count() % 2 == 1
    assert word.hexadecimal == f"0x{word.value:08X}"


def test_even_parity_is_generated_when_explicitly_configured() -> None:
    word = generate_word(make_instrument(config=bnr_config("even")), 1)

    assert word.value.bit_count() % 2 == 0


def test_missing_configuration_blocks_generation() -> None:
    with pytest.raises(ValueError, match="Falta la configuración"):
        generate_word(make_instrument(), 1)


def test_bnr_rejects_values_not_representable_at_configured_resolution() -> None:
    with pytest.raises(ValueError, match="no es representable"):
        generate_word(make_instrument(config=bnr_config()), 0.3)


def test_bcd_uses_only_explicit_digit_mapping() -> None:
    config = {
        "label_base": "decimal",
        "label_bit_order": "normal",
        "parity": "odd",
        "data": {
            "decimal_places": 0,
            "digit_bit_positions": [[0, 1, 2, 3]],
        },
    }
    word = generate_word(
        make_instrument(EncodingType.BCD, config, minimum=0, maximum=9), 7
    )

    assert (word.value >> 3) & 0b1111 == 7


def test_discrete_rejects_unmapped_state() -> None:
    config = {
        "label_base": "decimal",
        "label_bit_order": "normal",
        "parity": "odd",
        "data": {"value_map": {"0": 1, "1": 2}},
    }
    instrument = make_instrument(
        EncodingType.DISCRETE, config, minimum=0, maximum=2
    )

    with pytest.raises(ValueError, match="no está definido"):
        generate_word(instrument, 2)


def test_label_reversal_is_configurable() -> None:
    config = bnr_config()
    config["label_bit_order"] = "reversed"
    word = generate_word(make_instrument(config=config), 0)

    assert word.value >> 24 == 0b10000000
