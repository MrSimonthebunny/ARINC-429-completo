import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import serial
from PySide6.QtWidgets import QApplication

from arinc429.domain.models import EncodingType, Instrument
from arinc429.domain.word import ArincWord
from arinc429.infrastructure.database import Database
from arinc429.presentation.main_window import MainWindow


def test_serial_failure_is_shown_and_saved_in_history(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(Database(tmp_path / "serial-error.sqlite3"))
    instrument = window.instruments.save_instrument(
        Instrument(
            id=None,
            name="Altímetro",
            minimum=-10,
            maximum=10,
            label="1",
            encoding=EncodingType.BNR,
            resolution=1,
            unit="ft",
            sdi=0,
            ssm=0,
            encoding_config="{}",
        )
    )
    record = window.transmissions.create_transmission(
        instrument.id, 1, word_hex="0x00000000"
    )
    window.current_word = ArincWord(0)
    window.current_transmission = record
    window.serial_port.setEditText("INVALID")
    errors: list[str] = []
    window._show_error = errors.append

    def fail_transmission(*args, **kwargs):
        raise serial.SerialException("port unavailable")

    window.serial_output.transmit = fail_transmission
    window.transmit_serial()

    history = window.transmissions.list_transmissions()
    saved = history[0]
    assert saved.id != record.id
    assert saved.output == "Serial"
    assert saved.status == "Error"
    assert "port unavailable" in saved.details
    assert window.transmissions.get_transmission(record.id) == record
    assert errors and "port unavailable" in errors[0]
    window.close()


def test_changing_value_invalidates_previous_word_before_serial_send(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(Database(tmp_path / "stale-word.sqlite3"))
    instrument = window.instruments.save_instrument(
        Instrument(
            id=None,
            name="Altímetro",
            minimum=-10,
            maximum=10,
            label="1",
            encoding=EncodingType.BNR,
            resolution=1,
            unit="ft",
            sdi=0,
            ssm=0,
            encoding_config="{}",
        )
    )
    window.refresh_instruments()
    window.current_word = ArincWord(0x12345678)
    record = window.transmissions.create_transmission(instrument.id, 1)
    window.current_transmission = record
    window.current_instrument = instrument
    window.transmission_value.setValue(2)
    errors: list[str] = []
    window._show_error = errors.append

    window.transmit_serial()

    assert window.current_word is None
    assert errors and "Genere una palabra" in errors[0]
    assert window.transmissions.list_transmissions() == [record]
    window.close()
