"""Schnitttabelle aus Excel lesen: eine Zeile pro QP.

QP | KM | Mast 1 | X1 | Y1 | Mast 2 | X2 | Y2, optional Nullpunkt X | Nullpunkt Y | Nullpunkt Z.
X = E, Y = N (LV95).
"""

import numpy as np
import openpyxl

from .config import EXCEL_COLUMNS, EXCEL_ZERO_POINT, ZERO_POINT_NOTICE
from .model import DataError, Section


def cell_text(value):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def read_sections(xlsx_path):
    """Liefert (Querprofile, Meldungen). Meldungen sind WARNUNG- und HINWEIS-Zeilen."""
    ws = openpyxl.load_workbook(xlsx_path, data_only=True).active
    rows = ws.iter_rows(values_only=True)
    header = [cell_text(h) if h is not None else "" for h in next(rows)]
    try:
        col = {key: header.index(name) for key, name in EXCEL_COLUMNS.items()}
    except ValueError as exc:
        raise DataError(f"Spalte fehlt in {xlsx_path.name}: {exc}. Kopfzeile: {header}") from None
    zero_cols = [header.index(n) for n in EXCEL_ZERO_POINT] if set(EXCEL_ZERO_POINT) <= set(header) else None

    sections, messages = [], []
    for row in rows:
        if row[col["qp"]] is None:
            continue
        qp = cell_text(row[col["qp"]])
        coords = [row[col[key]] for key in ("e1", "n1", "e2", "n2")]
        if any(v is None for v in coords):
            messages.append(f"WARNUNG QP {qp}: Koordinaten unvollständig, übersprungen")
            continue
        zero = [row[c] for c in zero_cols] if zero_cols else []
        km = row[col["km"]]
        sec = Section(
            qp=qp,
            km=float(km) if km is not None else None,
            masts=(cell_text(row[col["mast1"]] or ""), cell_text(row[col["mast2"]] or "")),
            start=np.array(coords[:2], float),
            end=np.array(coords[2:], float),
            zero_point=np.array(zero, float) if zero and None not in zero else None,
        )
        if abs(sec.offset) > ZERO_POINT_NOTICE:
            messages.append(f"HINWEIS {sec.title}: NP liegt {sec.offset:.2f} m neben der Mastlinie, "
                            "Schnitt parallel durch NP gelegt")
        sections.append(sec)
    return sections, messages
