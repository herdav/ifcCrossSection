"""DXF der Querprofile schreiben.

Bezug LV95:
  QP01_km64.601.dxf      2D-Profil: x = Station ab Punkt 1 [m], y = Höhe [m ü. M.]
  QP01_km64.601_3D.dxf   3D-Polylinien in LV95 / LN02
Bezug NP:
  QP01_km64.601_NP.dxf   2D-Profil mit Nullpunkt des QP auf 0,0, dort Kreuz mit Koordinaten

DXF-Texte nur ASCII ohne Binde- oder Gedankenstriche (txt.shx zeigt sie als "?").
"""

import math
import re

import ezdxf
import numpy as np
from ezdxf.enums import TextEntityAlignment

from .checks import terrain_warnings
from .config import (
    LAYER_BREAKLINE, LAYER_MAST, LAYER_RAIL, LAYER_TEXT, LAYER_ZERO, MARK_SIZE, MAST_OVERHANG, RAIL_LAYER,
    REF_LV95, REF_NP, STATUS_COLORS, TEXT_HEIGHT, ZH_NONE, ZH_RAILS,
)
from .cutting import extents, reference_shift, section_lines, section_marks, terrain_height, to_profile
from .model import CutSettings

ASCII_REPLACE = {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss",
                 "–": " ", "—": " ", "-": " ", "‐": " "}


def ascii_text(text):
    """Nur ASCII, ohne Binde- und Gedankenstriche (txt.shx zeigt sie als "?")."""
    for a, b in ASCII_REPLACE.items():
        text = text.replace(a, b)
    return text.encode("ascii", "replace").decode("ascii")


def layer_name(status):
    return "GELAENDE_" + re.sub(r'[<>/\\":;?*|=`,]', "_", ascii_text(status)).upper()


def new_doc(statuses):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.M
    for status in statuses:
        doc.layers.add(layer_name(status), color=STATUS_COLORS.get(status, 3))
    doc.layers.add(LAYER_MAST, color=4)
    doc.layers.add(LAYER_TEXT, color=7)
    return doc


def add_text(msp, text, pos, height=TEXT_HEIGHT, align=TextEntityAlignment.BOTTOM_CENTER, rotation=0.0,
             layer=LAYER_TEXT):
    msp.add_text(ascii_text(text), height=height, rotation=rotation,
                 dxfattribs={"layer": layer}).set_placement(pos, align=align)


def add_zero_point(msp, zero_point, height, y=0.0):
    """Kreuz beim NP (Station 0, y) mit den Landeskoordinaten und der verwendeten Höhe."""
    r = TEXT_HEIGHT
    msp.add_line((-r, y), (r, y), dxfattribs={"layer": LAYER_ZERO})
    msp.add_line((0, y - r), (0, y + r), dxfattribs={"layer": LAYER_ZERO})
    e, n, _ = zero_point
    add_text(msp, f"NP E {e:.3f} N {n:.3f} H {height:.3f}", (0.6 * r, y + 0.3 * r), 0.6 * TEXT_HEIGHT,
             TextEntityAlignment.BOTTOM_LEFT, layer=LAYER_ZERO)


def add_marks(doc, msp, marks, to_xy):
    """Schienen als Dreieck auf SOK, übrige Bruchkanten als Kreuz mit Code."""
    if not marks:
        return
    for layer, color in ((LAYER_RAIL, 5), (LAYER_BREAKLINE, 3)):
        if layer not in doc.layers:
            doc.layers.add(layer, color=color)
    m = MARK_SIZE
    for code, point, station in marks:
        x, y = to_xy(point, station)
        if code == RAIL_LAYER:
            msp.add_lwpolyline([(x - m, y + 1.5 * m), (x, y), (x + m, y + 1.5 * m)], close=True,
                               dxfattribs={"layer": LAYER_RAIL})
        else:
            msp.add_line((x - m, y - m), (x + m, y + m), dxfattribs={"layer": LAYER_BREAKLINE})
            msp.add_line((x - m, y + m), (x + m, y - m), dxfattribs={"layer": LAYER_BREAKLINE})
            add_text(msp, code, (x, y + 2 * m), 0.5 * TEXT_HEIGHT, TextEntityAlignment.BOTTOM_LEFT, 60.0,
                     layer=LAYER_BREAKLINE)


def save(doc, path):
    try:
        doc.saveas(path)
        return path.name
    except PermissionError:
        return f"FEHLER {path.name} gesperrt (in CAD geöffnet?)"


def zero_height(sec, settings, shift):
    """Höhe, die im Bezug NP als NP gilt (für Kreuz und Text)."""
    if settings.zero_height == ZH_NONE:
        return sec.zero_point[2]
    return shift[1]


def write_section(sec, terrain, out_dir, reference=REF_LV95, settings=None):
    """Schreibt die DXF eines QP und liefert eine Protokollzeile.

    LV95: 2D-Profil (Höhe m ü. M.) und 3D in Landeskoordinaten.
    NP:   nur 2D-Profil, der Nullpunkt des QP liegt auf 0,0.
    """
    settings = settings or CutSettings()
    if sec.length == 0:
        return f"FEHLER {sec.title}: beide Punkte identisch, nicht exportiert"
    if reference == REF_NP and sec.zero_point is None:
        return f"FEHLER {sec.title}: kein Nullpunkt, nicht exportiert"
    lines = section_lines(sec, terrain, settings)
    marks = section_marks(sec, terrain, settings)
    shift = reference_shift(sec, reference, settings, marks)
    if shift[1] is None:
        return f"FEHLER {sec.title}: keine Schienen am NP für die bestehende SOK, nicht exportiert"
    profile = to_profile(lines, shift)
    masts = [(station - shift[0], label, point) for station, _, label, point, _ in sec.mast_points()]
    mast_stations = [s for s, _, _ in masts] or [-shift[0]]

    if lines:
        all_s = np.concatenate([s for _, s, _ in profile])
        all_z = np.concatenate([z for *_, z in profile] + [np.array([p[2] for _, p, _ in marks]) - shift[1]])
        z_min, z_max, s_min = all_z.min(), all_z.max(), min(all_s.min(), *mast_stations)
    else:
        z_min = z_max = 0.0
        s_min = min(mast_stations)
    z_low, z_top = z_min - MAST_OVERHANG, z_max + MAST_OVERHANG
    statuses = sorted({status for status, _, _ in lines})

    # 2D-Profil: x = Station, y = Höhe (LV95: ab Punkt 1 / m ü. M., NP: ab Nullpunkt)
    doc = new_doc(statuses)
    msp = doc.modelspace()
    for status, stations, heights in profile:
        msp.add_lwpolyline(np.column_stack([stations, heights]).tolist(), dxfattribs={"layer": layer_name(status)})
    for station, label, _ in masts:
        msp.add_line((station, z_low), (station, z_top), dxfattribs={"layer": LAYER_MAST})
        add_text(msp, label, (station, z_top + 0.2 * TEXT_HEIGHT))
    add_text(msp, sec.title, (s_min, z_top + 3 * TEXT_HEIGHT), 2 * TEXT_HEIGHT, TextEntityAlignment.BOTTOM_LEFT)
    add_marks(doc, msp, marks, lambda p, s: (s - shift[0], p[2] - shift[1]))

    if reference == REF_NP:
        doc.layers.add(LAYER_ZERO, color=6)
        height = zero_height(sec, settings, shift)
        add_zero_point(msp, sec.zero_point, height, height - shift[1])
        names = [save(doc, out_dir / f"{sec.file_stem}_NP.dxf")]
    else:
        names = [save(doc, out_dir / f"{sec.file_stem}.dxf")]

        # 3D in LV95: Masten an ihrer echten Lage, Texte horizontal und in der Situation lesbar
        doc = new_doc(statuses)
        msp = doc.modelspace()
        for status, pts, _ in lines:
            msp.add_polyline3d(pts.tolist(), dxfattribs={"layer": layer_name(status)})
        for _, label, (e, n) in masts:
            msp.add_line((e, n, z_low), (e, n, z_top), dxfattribs={"layer": LAYER_MAST})
            add_text(msp, label, (e, n, z_top + 0.2 * TEXT_HEIGHT))
        e, n = sec.origin + s_min * sec.direction
        rotation = math.degrees(math.atan2(sec.direction[1], sec.direction[0]))
        add_text(msp, sec.title, (e, n, z_top), 2 * TEXT_HEIGHT, TextEntityAlignment.BOTTOM_LEFT, rotation)
        if marks:
            doc.layers.add(LAYER_RAIL, color=5)
            doc.layers.add(LAYER_BREAKLINE, color=3)
        for code, point, _ in marks:
            msp.add_point(point.tolist(), dxfattribs={"layer": LAYER_RAIL if code == RAIL_LAYER else LAYER_BREAKLINE})
        names.append(save(doc, out_dir / f"{sec.file_stem}_3D.dxf"))

    sec.terrain_warnings = terrain_warnings(sec, lines)
    if lines:
        info = f"{len(lines)} Linien, Station {all_s.min():.1f} bis {all_s.max():.1f} m"
        info += "".join(f"; {w}" for w in describe_section(sec, lines, marks, settings))
    else:
        info = "WARNUNG Schnitt trifft kein Gelände"
    log = f"{sec.title}: {info} -> {', '.join(names)}"
    return "\n".join([log] + [f"WARNUNG {sec.title}: {w}" for w in sec.terrain_warnings])


def describe_section(sec, lines, marks, settings):
    """Zusatzangaben fürs Protokoll: Breite des Geländes ab NP je Status, Gelände am Mast, Schienen."""
    parts = []
    if sec.zero_point is not None:
        mast_side = {("links" if s < sec.zero_station else "rechts") for s, *_ in sec.mast_points()}
        side = f", Mast {' und '.join(sorted(mast_side))}" if any(sec.mast_info) and mast_side else ""
        for status, (lo, hi) in extents(lines).items():
            parts.append(f"{status} ab NP links {max(sec.zero_station - lo, 0):.1f} m, "
                         f"rechts {max(hi - sec.zero_station, 0):.1f} m{side}")
        rails = sorted(s - sec.zero_station for code, _, s in marks if code == RAIL_LAYER)
        if settings.zero_height == ZH_RAILS or rails:
            parts.append("Schienen ab NP " + (" / ".join(f"{s:+.2f}" for s in rails) if rails else "keine"))
    for station, name, _, _, info in sec.mast_points():
        found = terrain_height(lines, station) if info else None
        if found:
            parts.append(f"Gelände am Mast {name} {found[1]:.2f}")
    return parts


def export_sections(sections, terrain, out_dir, reference=REF_LV95, settings=None):
    """Schreibt die DXF mehrerer QP nach out_dir und liefert die Protokollzeilen."""
    stems = [s.file_stem for s in sections]
    log = [f"WARNUNG {stem} kommt mehrfach vor, Datei wird überschrieben"
           for stem in sorted({s for s in stems if stems.count(s) > 1})]
    out_dir.mkdir(parents=True, exist_ok=True)
    for sec in sections:
        log += write_section(sec, terrain, out_dir, reference, settings).splitlines()
    return log
