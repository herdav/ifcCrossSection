"""Hintergrund-Threads, damit das Fenster beim Laden bedienbar bleibt."""

from PySide6.QtCore import QThread, Signal

from core.terrain import load_terrain


class TerrainLoader(QThread):
    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, paths):
        super().__init__()
        self.paths = paths

    def run(self):
        try:
            self.loaded.emit(load_terrain(self.paths))
        except Exception as exc:
            self.failed.emit(str(exc))
