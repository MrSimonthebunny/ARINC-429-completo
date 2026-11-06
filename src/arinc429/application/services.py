from dataclasses import replace

from arinc429.domain.models import Instrument, Transmission
from arinc429.domain.word import ArincWord, generate_word
from arinc429.infrastructure.database import (
    InstrumentRepository,
    TransmissionRepository,
)


class InstrumentService:
    def __init__(self, repository: InstrumentRepository) -> None:
        self.repository = repository

    def list_instruments(self) -> list[Instrument]:
        return self.repository.list_all()

    def get_instrument(self, instrument_id: int) -> Instrument | None:
        return self.repository.get(instrument_id)

    def save_instrument(self, instrument: Instrument) -> Instrument:
        return self.repository.save(instrument)

    def delete_instrument(self, instrument_id: int) -> None:
        self.repository.delete(instrument_id)

    def generate_word(self, instrument_id: int, value: float) -> ArincWord:
        instrument = self.repository.get(instrument_id)
        if instrument is None:
            raise ValueError("El instrumento seleccionado ya no existe.")
        return generate_word(instrument, value)


class TransmissionService:
    def __init__(
        self,
        instruments: InstrumentRepository,
        transmissions: TransmissionRepository,
    ) -> None:
        self.instruments = instruments
        self.transmissions = transmissions

    def list_transmissions(self) -> list[Transmission]:
        return self.transmissions.list_all()

    def get_transmission(self, transmission_id: int) -> Transmission | None:
        return self.transmissions.get(transmission_id)

    def create_transmission(
        self,
        instrument_id: int,
        value: float,
        output: str = "Pendiente",
        status: str = "Pendiente",
        details: str = "",
        word_hex: str = "",
        word_binary: str = "",
    ) -> Transmission:
        instrument = self.instruments.get(instrument_id)
        if instrument is None:
            raise ValueError("El instrumento seleccionado ya no existe.")
        transmission = Transmission.create(
            instrument,
            value,
            output,
            status,
            details,
            word_hex,
            word_binary,
        )
        return self.transmissions.save(transmission)

    def update_transmission(self, transmission: Transmission) -> Transmission:
        if transmission.instrument_id is None:
            raise ValueError("El envío no está asociado a un instrumento existente.")
        instrument = self.instruments.get(transmission.instrument_id)
        if instrument is None:
            raise ValueError("El instrumento seleccionado ya no existe.")
        instrument.validate_value(transmission.value)
        return self.transmissions.save(replace(transmission, instrument_name=instrument.name))

    def record_output_event(
        self,
        output: str,
        value: float,
        status: str,
        details: str,
        instrument_id: int | None = None,
        instrument_name: str | None = None,
        word_hex: str = "",
        word_binary: str = "",
    ) -> Transmission:
        return self.transmissions.save(
            Transmission.create_output_event(
                output,
                value,
                status,
                details,
                instrument_id=instrument_id,
                instrument_name=instrument_name or "Salida de audio",
                word_hex=word_hex,
                word_binary=word_binary,
            )
        )

    def delete_transmission(self, transmission_id: int) -> None:
        self.transmissions.delete(transmission_id)
