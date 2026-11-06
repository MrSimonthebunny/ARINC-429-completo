import os
import sqlite3
import sys
from pathlib import Path

from arinc429.domain.models import EncodingType, Instrument, Transmission

SCHEMA = """
CREATE TABLE IF NOT EXISTS instruments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    minimum REAL NOT NULL,
    maximum REAL NOT NULL,
    label TEXT NOT NULL,
    encoding TEXT NOT NULL,
    resolution REAL NOT NULL,
    unit TEXT NOT NULL,
    sdi INTEGER NOT NULL,
    ssm INTEGER NOT NULL,
    encoding_config TEXT
);
CREATE TABLE IF NOT EXISTS transmissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument_id INTEGER REFERENCES instruments(id) ON DELETE SET NULL,
    instrument_name TEXT NOT NULL,
    value REAL NOT NULL,
    output TEXT NOT NULL,
    status TEXT NOT NULL,
    details TEXT NOT NULL,
    word_hex TEXT NOT NULL,
    word_binary TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            if os.name == "nt":
                base_directory = Path(
                    os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
                )
            elif sys.platform == "darwin":
                base_directory = Path.home() / "Library" / "Application Support"
            else:
                base_directory = Path.home() / ".local" / "share"
            data_directory = base_directory / "arinc429-completo"
            data_directory.mkdir(parents=True, exist_ok=True)
            path = data_directory / "arinc429.sqlite3"
        self.path = str(path)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)


class InstrumentRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _to_model(row: sqlite3.Row) -> Instrument:
        return Instrument(
            id=row["id"],
            name=row["name"],
            minimum=row["minimum"],
            maximum=row["maximum"],
            label=row["label"],
            encoding=EncodingType(row["encoding"]),
            resolution=row["resolution"],
            unit=row["unit"],
            sdi=row["sdi"],
            ssm=row["ssm"],
            encoding_config=row["encoding_config"],
        )

    def list_all(self) -> list[Instrument]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM instruments ORDER BY name, id"
            ).fetchall()
        return [self._to_model(row) for row in rows]

    def get(self, instrument_id: int) -> Instrument | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM instruments WHERE id = ?", (instrument_id,)
            ).fetchone()
        return self._to_model(row) if row else None

    def save(self, instrument: Instrument) -> Instrument:
        values = (
            instrument.name.strip(),
            instrument.minimum,
            instrument.maximum,
            instrument.label.strip(),
            instrument.encoding.value,
            instrument.resolution,
            instrument.unit.strip(),
            instrument.sdi,
            instrument.ssm,
            instrument.encoding_config,
        )
        with self.database.connect() as connection:
            if instrument.id is None:
                cursor = connection.execute(
                    """INSERT INTO instruments
                    (name, minimum, maximum, label, encoding, resolution,
                     unit, sdi, ssm, encoding_config)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    values,
                )
                instrument_id = cursor.lastrowid
            else:
                connection.execute(
                    """UPDATE instruments SET name=?, minimum=?, maximum=?,
                    label=?, encoding=?, resolution=?, unit=?, sdi=?, ssm=?,
                    encoding_config=? WHERE id=?""",
                    (*values, instrument.id),
                )
                instrument_id = instrument.id
        if instrument_id is None:
            raise RuntimeError("SQLite no devolvió el ID del instrumento guardado.")
        saved = self.get(instrument_id)
        if saved is None:
            raise RuntimeError("No se pudo recuperar el instrumento recién guardado.")
        return saved

    def delete(self, instrument_id: int) -> None:
        with self.database.connect() as connection:
            connection.execute("DELETE FROM instruments WHERE id = ?", (instrument_id,))


class TransmissionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _to_model(row: sqlite3.Row) -> Transmission:
        return Transmission(
            id=row["id"],
            instrument_id=row["instrument_id"],
            instrument_name=row["instrument_name"],
            value=row["value"],
            output=row["output"],
            status=row["status"],
            details=row["details"],
            word_hex=row["word_hex"],
            word_binary=row["word_binary"],
            created_at=row["created_at"],
        )

    def list_all(self) -> list[Transmission]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM transmissions ORDER BY id DESC"
            ).fetchall()
        return [self._to_model(row) for row in rows]

    def get(self, transmission_id: int) -> Transmission | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM transmissions WHERE id = ?", (transmission_id,)
            ).fetchone()
        return self._to_model(row) if row else None

    def save(self, transmission: Transmission) -> Transmission:
        values = (
            transmission.instrument_id,
            transmission.instrument_name,
            transmission.value,
            transmission.output,
            transmission.status,
            transmission.details,
            transmission.word_hex,
            transmission.word_binary,
            transmission.created_at,
        )
        with self.database.connect() as connection:
            if transmission.id is None:
                cursor = connection.execute(
                    """INSERT INTO transmissions
                    (instrument_id, instrument_name, value, output, status,
                     details, word_hex, word_binary, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    values,
                )
                transmission_id = cursor.lastrowid
            else:
                connection.execute(
                    """UPDATE transmissions SET instrument_id=?,
                    instrument_name=?, value=?, output=?, status=?, details=?,
                    word_hex=?, word_binary=?, created_at=? WHERE id=?""",
                    (*values, transmission.id),
                )
                transmission_id = transmission.id
        if transmission_id is None:
            raise RuntimeError("SQLite no devolvió el ID del envío guardado.")
        saved = self.get(transmission_id)
        if saved is None:
            raise RuntimeError("No se pudo recuperar el envío recién guardado.")
        return saved

    def delete(self, transmission_id: int) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM transmissions WHERE id = ?", (transmission_id,)
            )
