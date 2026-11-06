import json
import math
from dataclasses import dataclass
from typing import Any

from arinc429.domain.models import EncodingType, Instrument

DATA_WIDTH = 19
WORD_WIDTH = 32
DATA_MASK = (1 << DATA_WIDTH) - 1


@dataclass(frozen=True)
class ArincWord:
    value: int

    @property
    def binary(self) -> str:
        return f"{self.value:032b}"

    @property
    def hexadecimal(self) -> str:
        return f"0x{self.value:08X}"

    @property
    def bytes_big_endian(self) -> bytes:
        return self.value.to_bytes(4, byteorder="big")


def _read_config(instrument: Instrument) -> dict[str, Any]:
    if not instrument.encoding_config:
        raise ValueError(
            "Falta la configuración de codificación de este instrumento. "
            "Complete el esquema de configuración antes de generar la palabra."
        )
    try:
        config = json.loads(instrument.encoding_config)
    except json.JSONDecodeError as error:
        raise ValueError(f"La configuración no es JSON válido: {error.msg}.") from error
    if not isinstance(config, dict):
        raise ValueError("La configuración debe ser un objeto JSON.")
    for key in ("label_base", "label_bit_order", "parity"):
        if key not in config:
            raise ValueError(f"Falta el parámetro de codificación '{key}'.")
    if config["label_base"] not in ("octal", "decimal", "hexadecimal", "binary"):
        raise ValueError("label_base debe ser octal, decimal, hexadecimal o binary.")
    if config["label_bit_order"] not in ("normal", "reversed"):
        raise ValueError("label_bit_order debe ser normal o reversed.")
    if config["parity"] not in ("odd", "even"):
        raise ValueError("parity debe ser odd o even.")
    return config


def _parse_label(label: str, base: str) -> int:
    radix = {"octal": 8, "decimal": 10, "hexadecimal": 16, "binary": 2}[base]
    try:
        parsed = int(label.strip(), radix)
    except ValueError as error:
        raise ValueError(f"El label no es válido en base {base}.") from error
    if not 0 <= parsed <= 0xFF:
        raise ValueError("El label debe caber en 8 bits.")
    return parsed


def _validate_positions(positions: Any, expected: int) -> list[int]:
    if (
        not isinstance(positions, list)
        or len(positions) != expected
        or any(type(position) is not int or not 0 <= position < DATA_WIDTH for position in positions)
        or len(set(positions)) != expected
    ):
        raise ValueError(
            f"data_bit_positions debe indicar {expected} posiciones distintas "
            f"entre 0 y 18 (posición 0 = bit 11 de la palabra)."
        )
    return positions


def _encode_bnr(
    instrument: Instrument, value: float, config: dict[str, Any]
) -> int:
    required = ("zero_value", "representation", "data_bit_positions")
    for key in required:
        if key not in config:
            raise ValueError(f"Falta el parámetro BNR '{key}'.")
    data_lsb = instrument.resolution
    zero_value = config["zero_value"]
    if (
        type(zero_value) not in (int, float)
        or not math.isfinite(zero_value)
    ):
        raise ValueError("zero_value debe ser finito.")
    representation = config["representation"]
    if representation not in ("unsigned", "twos_complement", "sign_magnitude"):
        raise ValueError("BNR representation debe ser unsigned, twos_complement o sign_magnitude.")
    raw = (value - zero_value) / data_lsb
    quantized = round(raw)
    if not math.isclose(raw, quantized, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("El valor no es representable con el data_lsb configurado.")
    if representation == "unsigned":
        if not 0 <= quantized <= DATA_MASK:
            raise ValueError("El valor codificado excede el rango BNR unsigned de 19 bits.")
        encoded = quantized
    elif representation == "twos_complement":
        if not -(1 << 18) <= quantized < (1 << 18):
            raise ValueError("El valor codificado excede el rango BNR signed de 19 bits.")
        encoded = quantized & DATA_MASK
    else:
        magnitude = abs(quantized)
        if magnitude >= (1 << 18):
            raise ValueError("La magnitud excede el rango BNR sign_magnitude de 19 bits.")
        sign_bit = config.get("sign_bit_position")
        if type(sign_bit) is not int or not 0 <= sign_bit < DATA_WIDTH:
            raise ValueError("sign_magnitude requiere un sign_bit_position entre 0 y 18.")
        encoded = 0
        magnitude_positions = [
            position for position in range(DATA_WIDTH) if position != sign_bit
        ]
        for source_bit, destination_bit in enumerate(magnitude_positions):
            encoded |= ((magnitude >> source_bit) & 1) << destination_bit
        if quantized < 0:
            encoded |= 1 << sign_bit
    positions = _validate_positions(config["data_bit_positions"], DATA_WIDTH)
    result = 0
    for source_bit, destination_bit in enumerate(positions):
        result |= ((encoded >> source_bit) & 1) << destination_bit
    return result


def _encode_bcd(value: float, config: dict[str, Any]) -> int:
    required = ("decimal_places", "digit_bit_positions")
    for key in required:
        if key not in config:
            raise ValueError(f"Falta el parámetro BCD '{key}'.")
    decimal_places = config["decimal_places"]
    digit_positions = config["digit_bit_positions"]
    if type(decimal_places) is not int or not 0 <= decimal_places <= 18:
        raise ValueError("decimal_places debe ser un entero entre 0 y 18.")
    if not isinstance(digit_positions, list) or not digit_positions:
        raise ValueError("digit_bit_positions debe ser una lista de posiciones por dígito.")
    scaled = value * (10**decimal_places)
    integer_value = round(scaled)
    if not math.isclose(scaled, integer_value, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("El valor no es representable con los decimales BCD configurados.")
    if integer_value < 0:
        sign_config = config.get("sign")
        if not isinstance(sign_config, dict):
            raise ValueError("Los valores negativos requieren configuración explícita de sign.")
        sign_position = sign_config.get("position")
        negative_value = sign_config.get("negative_value")
        positive_value = sign_config.get("positive_value")
        if type(sign_position) is not int or not 0 <= sign_position < DATA_WIDTH:
            raise ValueError("sign.position debe estar entre 0 y 18.")
        if (
            type(negative_value) is not int
            or type(positive_value) is not int
            or negative_value not in (0, 1)
            or positive_value not in (0, 1)
        ):
            raise ValueError("sign requiere negative_value y positive_value de 0 o 1.")
        sign_bit = negative_value
        integer_value = -integer_value
    else:
        sign_config = config.get("sign")
        if sign_config is not None:
            sign_position = sign_config.get("position")
            positive_value = sign_config.get("positive_value")
            if type(sign_position) is not int or not 0 <= sign_position < DATA_WIDTH:
                raise ValueError("sign.position debe estar entre 0 y 18.")
            if type(positive_value) is not int or positive_value not in (0, 1):
                raise ValueError("sign.positive_value debe ser 0 o 1.")
            sign_bit = positive_value
        else:
            sign_position = None
            sign_bit = 0

    result = 0
    occupied_positions: set[int] = set()
    for positions in digit_positions:
        digit_positions_checked = _validate_positions(positions, 4)
        if occupied_positions.intersection(digit_positions_checked):
            raise ValueError("Los dígitos BCD no pueden compartir posiciones de bit.")
        occupied_positions.update(digit_positions_checked)
        digit = integer_value % 10
        integer_value //= 10
        for source_bit, destination_bit in enumerate(digit_positions_checked):
            result |= ((digit >> source_bit) & 1) << destination_bit
    if integer_value:
        raise ValueError("El valor tiene más dígitos que los configurados.")
    if sign_position is not None:
        if sign_position in occupied_positions:
            raise ValueError("El bit de signo BCD no puede superponerse con un dígito.")
        result |= sign_bit << sign_position
    return result


def _encode_discrete(value: float, config: dict[str, Any]) -> int:
    value_map = config.get("value_map")
    if not isinstance(value_map, dict):
        raise ValueError("La codificación discreta requiere value_map explícito.")
    key = format(value, ".15g")
    if key not in value_map:
        raise ValueError(f"El estado {key} no está definido en value_map.")
    data = value_map[key]
    if type(data) is not int or not 0 <= data <= DATA_MASK:
        raise ValueError("Cada valor de value_map debe ser un entero de 19 bits.")
    return data


def generate_word(instrument: Instrument, value: float) -> ArincWord:
    instrument.validate_value(value)
    config = _read_config(instrument)
    label = _parse_label(instrument.label, config["label_base"])
    if config["label_bit_order"] == "reversed":
        label = int(f"{label:08b}"[::-1], 2)

    data_config = config.get("data")
    if not isinstance(data_config, dict):
        raise ValueError("Falta el objeto de configuración 'data'.")
    if instrument.encoding == EncodingType.BNR:
        data = _encode_bnr(instrument, value, data_config)
    elif instrument.encoding == EncodingType.BCD:
        data = _encode_bcd(value, data_config)
    elif instrument.encoding == EncodingType.DISCRETE:
        data = _encode_discrete(value, data_config)
    else:
        raise ValueError(f"Codificación no soportada: {instrument.encoding}.")

    word = (label << 24) | (instrument.sdi << 22) | (data << 3) | (instrument.ssm << 1)
    parity_bit = word.bit_count() & 1
    if config["parity"] == "odd":
        parity_bit ^= 1
    word |= parity_bit
    return ArincWord(word)
