"""Datenmodell: Geländefläche (Mesh) und Querprofil (Section)."""

from dataclasses import dataclass

import numpy as np

from .config import REF_NP


class DataError(Exception):
    """Eingabedaten unbrauchbar (fehlende Spalte, keine Georeferenz, ...)."""


@dataclass
class Mesh:
    status: str
    verts: np.ndarray  # (n, 3) LV95 / LN02
    faces: np.ndarray  # (m, 3) Indizes in verts


@dataclass
class Section:
    qp: str
    km: float | None
    masts: tuple[str, str]
    start: np.ndarray  # (E, N) Mast 1
    end: np.ndarray  # (E, N) Mast 2
    zero_point: np.ndarray | None = None  # (E, N, H) Nullpunkt, z. B. Gleisachse

    @property
    def title(self):
        return f"QP {self.qp}" + (f" km {self.km:.3f}" if self.km is not None else "")

    @property
    def file_stem(self):
        qp = f"QP{int(self.qp):02d}" if self.qp.isdigit() else f"QP{self.qp}"
        return qp + (f"_km{self.km:.3f}" if self.km is not None else "")

    @property
    def length(self):
        return float(np.linalg.norm(self.end - self.start))

    @property
    def direction(self):
        return (self.end - self.start) / self.length

    @property
    def offset(self):
        """Abstand des NP von der Mastlinie (links positiv); um so viel wird der Schnitt verschoben."""
        if self.zero_point is None or self.length == 0:
            return 0.0
        normal = np.array([-self.direction[1], self.direction[0]])
        return float((self.zero_point[:2] - self.start) @ normal)

    @property
    def origin(self):
        """Station 0 der Schnittlinie: Mast 1, parallel auf die Linie durch den NP verschoben."""
        return self.start + self.offset * np.array([-self.direction[1], self.direction[0]])

    @property
    def zero_station(self):
        if self.zero_point is None:
            return None
        return float((self.zero_point[:2] - self.origin) @ self.direction)

    def shift(self, reference):
        """(Station, Höhe) des Bezugspunkts: im Bezug NP der Nullpunkt, sonst bzw. ohne NP 0,0."""
        if reference == REF_NP and self.zero_point is not None:
            return self.zero_station, self.zero_point[2]
        return 0.0, 0.0
