import sys

from PySide6.QtWidgets import QApplication

from arinc429.presentation.main_window import MainWindow


def main() -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    window = MainWindow()
    window.show()
    return app.exec()
