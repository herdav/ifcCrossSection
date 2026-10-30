"""Projektdatei (.gsproj, JSON): Pfade relativ zur Projektdatei, Schnitte inklusive Änderungen."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import OUTPUT_DIR, REF_LV95
from .model import Section

PROJECT_SUFFIX = ".gsproj"
PROJECT_VERSION = 1


def section_to_dict(sec):
    return {"qp": sec.qp, "km": sec.km, "masts": list(sec.masts), "start": sec.start.tolist(),
            "end": sec.end.tolist(), "zero_point": None if sec.zero_point is None else sec.zero_point.tolist()}


def section_from_dict(d):
    masts = list(d.get("masts", [])) + ["", ""]
    zero = d.get("zero_point")
    return Section(str(d["qp"]), d.get("km"), (masts[0], masts[1]),
                   np.array(d["start"], float), np.array(d["end"], float),
                   None if zero is None else np.array(zero, float))


def relative(path, base):
    """Pfad relativ zur Projektdatei speichern, damit das Projekt mit dem Ordner umziehen kann."""
    try:
        return Path(os.path.relpath(path, base)).as_posix()
    except ValueError:  # anderes Laufwerk
        return Path(path).as_posix()


@dataclass
class Project:
    path: Path | None = None
    ifc_paths: list[Path] = field(default_factory=list)
    excel_path: Path | None = None
    out_dir: Path | None = None
    sections: list[Section] = field(default_factory=list)
    reference: str = REF_LV95
    exaggeration: float = 1.0
    current: int = 0

    @property
    def export_dir(self):
        """Gewählter Exportordner, sonst output/ neben der Projektdatei, ohne Projektdatei data/output."""
        return self.out_dir or (self.path.parent / "output" if self.path else OUTPUT_DIR)

    @classmethod
    def load(cls, path):
        """Liest eine Projektdatei. Löst OSError, ValueError oder KeyError aus, wenn sie unbrauchbar ist."""
        path = Path(path).resolve()
        data = json.loads(path.read_text(encoding="utf-8"))

        def absolute(p):
            return (path.parent / p).resolve() if p else None

        return cls(
            path=path,
            ifc_paths=[absolute(p) for p in data.get("ifc", [])],
            excel_path=absolute(data.get("excel")),
            out_dir=absolute(data.get("output")),
            sections=[section_from_dict(d) for d in data.get("sections", [])],
            reference=data.get("reference", REF_LV95),
            exaggeration=float(data.get("exaggeration", 1.0)),
            current=int(data.get("current", 0)),
        )

    def save(self):
        base = self.path.parent
        data = {
            "version": PROJECT_VERSION,
            "ifc": [relative(p, base) for p in self.ifc_paths],
            "excel": relative(self.excel_path, base) if self.excel_path else None,
            "output": relative(self.out_dir, base) if self.out_dir else None,
            "exaggeration": self.exaggeration,
            "reference": self.reference,
            "current": self.current,
            "sections": [section_to_dict(s) for s in self.sections],
        }
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
