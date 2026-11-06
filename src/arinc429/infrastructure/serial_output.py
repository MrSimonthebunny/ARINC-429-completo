from dataclasses import dataclass

import serial
from serial.tools import list_ports

from arinc429.domain.word import ArincWord


@dataclass(frozen=True)
class SerialSettings:
    port: str
    baudrate: int = 115200
    bytesize: int = serial.EIGHTBITS
    parity: str = serial.PARITY_NONE
    stopbits: float = serial.STOPBITS_ONE


class SerialOutput:
    @staticmethod
    def available_ports() -> list[str]:
        return [port.device for port in list_ports.comports()]

    def transmit(self, word: ArincWord, settings: SerialSettings) -> str:
        payload = word.bytes_big_endian
        with serial.Serial(
            port=settings.port,
            baudrate=settings.baudrate,
            bytesize=settings.bytesize,
            parity=settings.parity,
            stopbits=settings.stopbits,
            timeout=1,
            write_timeout=2,
        ) as connection:
            written = connection.write(payload)
            connection.flush()
        if written != len(payload):
            raise serial.SerialTimeoutException(
                f"Se escribieron {written} de {len(payload)} bytes."
            )
        return payload.hex(" ").upper()
