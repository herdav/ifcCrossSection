"""App starten: QApplication, Dark Mode, Hauptfenster, optional Projektdatei öffnen."""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .main_window import APP_NAME, MainWindow
from .theme import apply_dark_theme


def run(project=None):
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    apply_dark_theme(app)
    window = MainWindow()
    window.show()
    if project:
        window.open_project(Path(project))
    sys.exit(app.exec())
