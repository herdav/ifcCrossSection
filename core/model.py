"""Datenmodell: Gelände (Mesh, Grid, Breakline), Querprofil (Section) und Schnitteinstellungen."""

from dataclasses import dataclass, field

import numpy as np

from .config import ZH_TABLE


class DataError(Exception):
    """Eingabedaten unbrauchbar (fehlende Spalte, keine Georeferenz, ...)."""


@dataclass
class Mesh:
    status: str
    verts: np.ndarray  # (n, 3) LV95 / LN02
    faces: np.ndarray  # (m, 3) Indizes in verts


@dataclass
class Grid:
    """Regelmässiges Höhenraster (z. B. swissALTI3D). Wird nur entlang der Schnittlinien trianguliert."""
    status: str
    x0: float  # E der ersten Spalte
    y0: float  # N der ersten Zeile
    step: float
    z: np.ndarray  # (ny, nx), NaN = keine Daten


@dataclass
class Breakline:
    """3D-Linie aus der Aufnahme (Schiene, Mauerkrone, ...); im Schnitt eine Marke."""
    code: str
    points: np.ndarray  # (n, 3) LV95 / LN02


@dataclass
class MastInfo:
    """Angaben aus der Fundamentliste zu einem Mast."""
    number: str
    mast_type: str = ""
    foundation: str = ""
    track: str = ""
    a: float | None = None  # Abstand Gleisachse bis Mastachse [m]
    kote: float | None = None  # Kote am Mast [m ü. M.], vermutlich neue SOK

    @property
    def label(self):
        return " ".join(t for t in (self.number, self.mast_type, self.foundation) if t)


@dataclass
class CutSettings:
    half_length: float | None = None  # m, Schnitt beidseits des NP (ohne NP: der Mitte); None = ganzes Gelände
    zero_height: str = ZH_TABLE  # Höhe des NP im Bezug NP: ZH_TABLE, ZH_RAILS oder ZH_NONE


@dataclass
class Section:
    qp: str
    km: float | None
    masts: tuple[str, str]  # Namen der beiden Punkte; ohne Namen keine Mastlinie (z. B. Fusspunkt)
    start: np.ndarray  # (E, N) Punkt 1, Blickrichtung: links
    end: np.ndarray  # (E, N) Punkt 2, rechts
    zero_point: np.ndarray | None = None  # (E, N, H) Nullpunkt, z. B. Gleisachse
    mast_info: tuple[MastInfo | None, MastInfo | None] = (None, None)  # je Punkt, aus der Fundamentliste
    warnings: list[str] = field(default_factory=list)  # Prüfungen der Tabelle, wird nicht gespeichert
    terrain_warnings: list[str] = field(default_factory=list)  # Prüfungen gegen das Gelände, nicht gespeichert

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
        """Station 0 der Schnittlinie: Punkt 1, parallel auf die Linie durch den NP verschoben."""
        return self.start + self.offset * np.array([-self.direction[1], self.direction[0]])

    @property
    def zero_station(self):
        if self.zero_point is None:
            return None
        return float((self.zero_point[:2] - self.origin) @ self.direction)

    @property
    def centre_station(self):
        """Mitte der Schnittlänge: der NP, ohne NP die Mitte zwischen den Punkten."""
        return self.zero_station if self.zero_point is not None else self.length / 2

    def mast_points(self):
        """(Station, Name, Beschriftung, Lage E/N, MastInfo) der Punkte mit Namen."""
        result = []
        for station, name, info, point in zip((0.0, self.length), self.masts, self.mast_info, (self.start, self.end)):
            if name:
                result.append((station, name, info.label if info else name, point, info))
        return result
