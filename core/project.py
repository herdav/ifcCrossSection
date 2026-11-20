"""Projektdatei (.gsproj, JSON): Pfade relativ zur Projektdatei, Schnitte inklusive Änderungen."""

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from .checks import check_sections
from .config import OUTPUT_DIR, REF_LV95, ZH_TABLE
from .model import CutSettings, MastInfo, Section

PROJECT_SUFFIX = ".gsproj"
PROJECT_VERSION = 2  # 2: Geländedateien unter "terrain", Mastangaben, Schnittlänge, NP-Höhe


def section_to_dict(sec):
    d = {"qp": sec.qp, "km": sec.km, "masts": list(sec.masts), "start": sec.start.tolist(),
         "end": sec.end.tolist(), "zero_point": None if sec.zero_point is None else sec.zero_point.tolist()}
    if any(sec.mast_info):
        d["mast_info"] = [asdict(info) if info else None for info in sec.mast_info]
    return d


def section_from_dict(d):
    masts = list(d.get("masts", [])) + ["", ""]
    zero = d.get("zero_point")
    infos = list(d.get("mast_info") or []) + [None, None]
    return Section(str(d["qp"]), d.get("km"), (masts[0], masts[1]),
                   np.array(d["start"], float), np.array(d["end"], float),
                   None if zero is None else np.array(zero, float),
                   tuple(MastInfo(**info) if info else None for info in infos[:2]))


def relative(path, base):
    """Pfad relativ zur Projektdatei speichern, damit das Projekt mit dem Ordner umziehen kann."""
    try:
        return Path(os.path.relpath(path, base)).as_posix()
    except ValueError:  # anderes Laufwerk
        return Path(path).as_posix()


@dataclass
class Project:
    path: Path | None = None
    terrain_paths: list[Path] = field(default_factory=list)  # IFC, LandXML, XYZ, DXF-Bruchkanten
    excel_path: Path | None = None
    out_dir: Path | None = None
    sections: list[Section] = field(default_factory=list)
    reference: str = REF_LV95
    exaggeration: float = 1.0
    current: int = 0
    half_length: float | None = None
    zero_height: str = ZH_TABLE
    messages: list[str] = field(default_factory=list)  # Prüfungen beim Laden, wird nicht gespeichert

    @property
    def export_dir(self):
        """Gewählter Exportordner, sonst output/ neben der Projektdatei, ohne Projektdatei data/output."""
        return self.out_dir or (self.path.parent / "output" if self.path else OUTPUT_DIR)

    @property
    def settings(self):
        return CutSettings(self.half_length, self.zero_height)

    @classmethod
    def load(cls, path):
        """Liest eine Projektdatei. Löst OSError, ValueError, KeyError oder TypeError aus, wenn sie unbrauchbar ist."""
        path = Path(path).resolve()
        data = json.loads(path.read_text(encoding="utf-8"))

        def absolute(p):
            return (path.parent / p).resolve() if p else None

        sections = [section_from_dict(d) for d in data.get("sections", [])]
        half_length = data.get("half_length")
        return cls(
            path=path,
            terrain_paths=[absolute(p) for p in data.get("terrain", data.get("ifc", []))],
            excel_path=absolute(data.get("excel")),
            out_dir=absolute(data.get("output")),
            sections=sections,
            reference=data.get("reference", REF_LV95),
            exaggeration=float(data.get("exaggeration", 1.0)),
            current=int(data.get("current", 0)),
            half_length=float(half_length) if half_length else None,
            zero_height=data.get("zero_height", ZH_TABLE),
            messages=check_sections(sections),
        )

    def save(self):
        base = self.path.parent
        data = {
            "version": PROJECT_VERSION,
            "terrain": [relative(p, base) for p in self.terrain_paths],
            "excel": relative(self.excel_path, base) if self.excel_path else None,
            "output": relative(self.out_dir, base) if self.out_dir else None,
            "exaggeration": self.exaggeration,
            "reference": self.reference,
            "half_length": self.half_length,
            "zero_height": self.zero_height,
            "current": self.current,
            "sections": [section_to_dict(s) for s in self.sections],
        }
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
