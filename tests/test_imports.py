import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from arinc429.app import main
from arinc429.infrastructure.database import Database
from arinc429.presentation.main_window import MainWindow


def test_main_window_can_be_created(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(Database(tmp_path / "window.sqlite3"))

    assert callable(main)
    assert window.windowTitle() == "ARINC-429-completo"
    window.close()
