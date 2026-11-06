import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class EncodingType(StrEnum):
    BNR = "BNR"
    BCD = "BCD"
    DISCRETE = "Discreta"


@dataclass(frozen=True)
class Instrument:
    id: int | None
    name: str
    minimum: float
    maximum: float
    label: str
    encoding: EncodingType
    resolution: float
    unit: str
    sdi: int
    ssm: int
    encoding_config: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("El nombre del instrumento es obligatorio.")
        if not math.isfinite(self.minimum) or not math.isfinite(self.maximum):
            raise ValueError("Los límites deben ser números finitos.")
        if self.minimum > self.maximum:
            raise ValueError("El valor mínimo no puede superar al máximo.")
        if not math.isfinite(self.resolution) or self.resolution <= 0:
            raise ValueError("La resolución debe ser mayor que cero.")
        if type(self.sdi) is not int or not 0 <= self.sdi <= 3:
            raise ValueError("SDI debe estar entre 0 y 3.")
        if type(self.ssm) is not int or not 0 <= self.ssm <= 3:
            raise ValueError("SSM debe estar entre 0 y 3.")

    def validate_value(self, value: float) -> None:
        if not math.isfinite(value):
            raise ValueError("El valor debe ser un número finito.")
        if not self.minimum <= value <= self.maximum:
            raise ValueError(
                f"El valor debe estar entre {self.minimum:g} y "
                f"{self.maximum:g} {self.unit}."
            )


@dataclass(frozen=True)
class Transmission:
    id: int | None
    instrument_id: int | None
    instrument_name: str
    value: float
    output: str
    status: str
    details: str
    word_hex: str = ""
    word_binary: str = ""
    created_at: str = ""

    @classmethod
    def create(
        cls,
        instrument: Instrument,
        value: float,
        output: str = "Pendiente",
        status: str = "Pendiente",
        details: str = "",
        word_hex: str = "",
        word_binary: str = "",
    ) -> "Transmission":
        instrument.validate_value(value)
        return cls(
            id=None,
            instrument_id=instrument.id,
            instrument_name=instrument.name,
            value=value,
            output=output,
            status=status,
            details=details,
            word_hex=word_hex,
            word_binary=word_binary,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    @classmethod
    def create_output_event(
        cls,
        output: str,
        value: float,
        status: str,
        details: str,
        instrument_id: int | None = None,
        instrument_name: str = "Salida de audio",
        word_hex: str = "",
        word_binary: str = "",
    ) -> "Transmission":
        if not math.isfinite(value):
            raise ValueError("El valor registrado debe ser finito.")
        return cls(
            id=None,
            instrument_id=instrument_id,
            instrument_name=instrument_name,
            value=value,
            output=output,
            status=status,
            details=details,
            word_hex=word_hex,
            word_binary=word_binary,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
