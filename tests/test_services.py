from dataclasses import replace

import pytest

from arinc429.application.services import InstrumentService, TransmissionService
from arinc429.domain.models import EncodingType, Instrument


def instrument(name: str = "Altímetro") -> Instrument:
    return Instrument(
        id=None,
        name=name,
        minimum=-100,
        maximum=100,
        label="1",
        encoding=EncodingType.BNR,
        resolution=0.5,
        unit="ft",
        sdi=0,
        ssm=0,
    )


def test_instrument_crud(repositories) -> None:
    instrument_repository, _ = repositories
    service = InstrumentService(instrument_repository)
    saved = service.save_instrument(instrument())

    assert saved.id is not None
    assert service.get_instrument(saved.id) == saved
    assert service.list_instruments() == [saved]

    updated = service.save_instrument(replace(saved, name="Altímetro principal"))
    assert updated.name == "Altímetro principal"
    assert service.get_instrument(saved.id) == updated

    service.delete_instrument(saved.id)
    assert service.get_instrument(saved.id) is None


def test_transmission_crud_and_range_validation(repositories) -> None:
    instrument_repository, transmission_repository = repositories
    instruments = InstrumentService(instrument_repository)
    saved_instrument = instruments.save_instrument(instrument())
    service = TransmissionService(instrument_repository, transmission_repository)

    with pytest.raises(ValueError, match="entre"):
        service.create_transmission(saved_instrument.id, 100.1)

    saved = service.create_transmission(saved_instrument.id, 25)
    assert service.get_transmission(saved.id) == saved
    assert service.list_transmissions() == [saved]

    updated = service.update_transmission(
        replace(saved, value=30, status="Modificado")
    )
    assert updated.value == 30
    assert updated.status == "Modificado"

    service.delete_transmission(updated.id)
    assert service.get_transmission(updated.id) is None


def test_deleting_instrument_preserves_transmission_history(repositories) -> None:
    instrument_repository, transmission_repository = repositories
    instruments = InstrumentService(instrument_repository)
    saved_instrument = instruments.save_instrument(instrument())
    service = TransmissionService(instrument_repository, transmission_repository)
    saved_transmission = service.create_transmission(saved_instrument.id, 10)

    instruments.delete_instrument(saved_instrument.id)

    history = service.list_transmissions()
    assert history[0].id == saved_transmission.id
    assert history[0].instrument_id is None
    assert history[0].instrument_name == saved_instrument.name


def test_output_events_are_saved_in_history(repositories) -> None:
    instrument_repository, transmission_repository = repositories
    service = TransmissionService(instrument_repository, transmission_repository)

    event = service.record_output_event(
        output="Audio",
        value=1000,
        status="Reproducción iniciada",
        details="Tono de prueba",
    )

    assert service.get_transmission(event.id) == event
    assert event.instrument_id is None
    assert event.instrument_name == "Salida de audio"
