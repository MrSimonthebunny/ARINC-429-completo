import pytest

from arinc429.infrastructure.database import (
    Database,
    InstrumentRepository,
    TransmissionRepository,
)


@pytest.fixture
def repositories(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    return (
        InstrumentRepository(database),
        TransmissionRepository(database),
    )
