"""Hintergrund-Threads, damit das Fenster beim Laden bedienbar bleibt."""

from PySide6.QtCore import QThread, Signal

from core.ifc_reader import load_meshes


class MeshLoader(QThread):
    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, paths):
        super().__init__()
        self.paths = paths

    def run(self):
        try:
            self.loaded.emit([mesh for path in self.paths for mesh in load_meshes(path)])
        except Exception as exc:
            self.failed.emit(str(exc))
