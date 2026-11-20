"""Querprofile aus der SBB-Vorlage «Fundamentliste» (Blatt LISTE) bauen.

Ein QP je Mastposten: ein Mast allein gibt einen Schnitt durch Mast und Fusspunkt (Lot auf die
Gleisachse), zwei Masten am selben km einen Schnitt durch beide. Der NP ist immer der Fusspunkt,
seine Höhe die Kote der Liste. Anker und Druckstützen bekommen kein eigenes QP.
Fehler der Liste werden nicht korrigiert, sondern von checks.check_sections gemeldet.
"""

import re

import numpy as np
from openpyxl.utils import column_index_from_string

from .checks import check_sections, km_groups
from .config import FOUNDATION_COLUMNS, FOUNDATION_FIRST_ROW
from .model import MastInfo, Section

STAY = re.compile(r"^\s*[AD]\s+zu\b", re.IGNORECASE)  # «A zu 52» Anker, «D zu 49» Druckstütze


def number(value):
    """Zahl aus Zelle (auch als Text mit Komma oder Apostroph), sonst None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("'", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def text(value):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return "" if value is None else str(value).strip()


def read_foundation_list(ws):
    """Liefert (Querprofile, Meldungen) aus dem Blatt der Fundamentliste."""
    col = {key: column_index_from_string(letter) - 1 for key, letter in FOUNDATION_COLUMNS.items()}
    masts, messages, stays = [], [], 0
    for row in ws.iter_rows(min_row=FOUNDATION_FIRST_ROW, values_only=True):
        row = list(row) + [None] * (max(col.values()) + 1 - len(row))
        km, name = number(row[col["km"]]), text(row[col["number"]])
        if km is None or not name:
            continue
        if STAY.match(name):
            stays += 1
            continue
        values = {key: number(row[col[key]]) for key in ("a", "foot_e", "foot_n", "mast_e", "mast_n", "kote")}
        if None in (values["foot_e"], values["foot_n"], values["mast_e"], values["mast_n"]):
            messages.append(f"WARNUNG Mast {name} km {km:.3f}: Koordinaten unvollständig, übersprungen")
            continue
        info = MastInfo(name, text(row[col["mast_type"]]), text(row[col["foundation"]]), text(row[col["track"]]),
                        values["a"], values["kote"])
        masts.append((round(km, 3), info, np.array([values["mast_e"], values["mast_n"]]),
                      np.array([values["foot_e"], values["foot_n"]])))

    sections = []
    for group in km_groups(sorted(masts, key=lambda m: m[0]), key=lambda m: m[0]):
        by_km = {}
        for m in group:
            by_km.setdefault(m[0], []).append(m)
        for km, members in by_km.items():
            for k in range(0, len(members), 2):  # mehr als zwei am selben km: paarweise in Listenreihenfolge
                sections.append(build_section(km, members[k:k + 2]))
    messages.append(f"{len(masts) + stays} Zeilen: {len(masts)} Masten, {stays} Anker oder Druckstützen, "
                    f"{len(sections)} Querprofile")
    return sections, messages + check_sections(sections)


def build_section(km, members):
    """QP durch einen Mast und seinen Fusspunkt oder durch zwei Masten; NP = Fusspunkt des ersten."""
    _, info, mast, foot = members[0]
    kotes = [m[1].kote for m in members if m[1].kote is not None]
    zero = np.array([*foot, np.mean(kotes) if kotes else 0.0])
    if len(members) == 1:
        # Blickrichtung wird in check_sections nach der Gleisrichtung gedreht
        return Section(info.number, km, ("", info.number), foot.copy(), mast.copy(), zero, (None, info))
    _, info2, mast2, _ = members[1]
    return Section(f"{info.number}+{info2.number}", km, (info.number, info2.number), mast.copy(), mast2.copy(),
                   zero, (info, info2))
