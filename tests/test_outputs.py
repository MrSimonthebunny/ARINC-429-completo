import pytest
import serial

from arinc429.domain.word import ArincWord
from arinc429.infrastructure.audio_output import AudioOutput
from arinc429.infrastructure.serial_output import SerialOutput, SerialSettings


def test_audio_signal_is_mono_16_bit_and_has_requested_duration() -> None:
    signal = AudioOutput.generate_signal(
        frequency=1000,
        amplitude=0.5,
        duration=1,
        sample_rate=44100,
    )

    assert signal.shape == (44100,)
    assert signal.dtype.name == "int16"
    assert signal.max() <= round(0.5 * 32767)
    assert signal.min() >= round(-0.5 * 32767)


def test_audio_rejects_frequency_above_nyquist() -> None:
    with pytest.raises(ValueError, match="Nyquist"):
        AudioOutput.generate_signal(frequency=22050)


def test_audio_uses_sounddevice_with_requested_samplerate(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakePortAudioError(Exception):
        pass

    class FakeSoundDevice:
        PortAudioError = FakePortAudioError

        @staticmethod
        def play(signal, **kwargs):
            calls["signal"] = signal
            calls["kwargs"] = kwargs

        @staticmethod
        def stop():
            calls["stopped"] = True

    monkeypatch.setattr(
        "arinc429.infrastructure.audio_output.import_module",
        lambda name: FakeSoundDevice,
    )
    output = AudioOutput()
    output.play()
    output.stop()

    assert calls["kwargs"] == {"samplerate": 44100, "blocking": False}
    assert calls["signal"].dtype.name == "int16"
    assert calls["stopped"] is True


def test_audio_device_failure_is_reported(monkeypatch) -> None:
    class FakePortAudioError(Exception):
        pass

    class FakeSoundDevice:
        PortAudioError = FakePortAudioError

        @staticmethod
        def play(*args, **kwargs):
            raise FakePortAudioError("device unavailable")

    monkeypatch.setattr(
        "arinc429.infrastructure.audio_output.import_module",
        lambda name: FakeSoundDevice,
    )
    with pytest.raises(RuntimeError, match="device unavailable"):
        AudioOutput().play()


def test_serial_uses_four_big_endian_bytes(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeSerial:
        def __init__(self, **kwargs):
            captured["settings"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def write(self, payload: bytes) -> int:
            captured["payload"] = payload
            return len(payload)

        def flush(self) -> None:
            pass

    monkeypatch.setattr("arinc429.infrastructure.serial_output.serial.Serial", FakeSerial)
    word = ArincWord(0x12345678)
    settings = SerialSettings(port="TEST")
    result = SerialOutput().transmit(word, settings)

    assert captured["payload"] == b"\x12\x34\x56\x78"
    assert captured["settings"]["baudrate"] == 115200
    assert captured["settings"]["bytesize"] == 8
    assert captured["settings"]["parity"] == serial.PARITY_NONE
    assert captured["settings"]["stopbits"] == serial.STOPBITS_ONE
    assert result == "12 34 56 78"


def test_serial_error_is_propagated(monkeypatch) -> None:
    def fail_to_open(**kwargs):
        raise serial.SerialException("port unavailable")

    monkeypatch.setattr("arinc429.infrastructure.serial_output.serial.Serial", fail_to_open)

    with pytest.raises(serial.SerialException, match="unavailable"):
        SerialOutput().transmit(ArincWord(0), SerialSettings(port="INVALID"))
