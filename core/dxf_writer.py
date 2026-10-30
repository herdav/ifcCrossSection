"""DXF der Querprofile schreiben.

Bezug LV95:
  QP01_km64.601.dxf      2D-Profil: x = Station ab Mast 1 [m], y = Höhe [m ü. M.]
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

from .config import (
    LAYER_MAST, LAYER_TEXT, LAYER_ZERO, MAST_OVERHANG, REF_LV95, REF_NP, STATUS_COLORS, TEXT_HEIGHT,
)
from .cutting import section_lines, to_profile


def layer_name(status):
    return "GELAENDE_" + re.sub(r'[<>/\\":;?*|=`,]', "_", status).upper()


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
    msp.add_text(text, height=height, rotation=rotation, dxfattribs={"layer": layer}).set_placement(pos, align=align)


def add_zero_point(msp, zero_point):
    """Kreuz bei 0,0 mit den Landeskoordinaten des Nullpunkts."""
    r = TEXT_HEIGHT
    msp.add_line((-r, 0), (r, 0), dxfattribs={"layer": LAYER_ZERO})
    msp.add_line((0, -r), (0, r), dxfattribs={"layer": LAYER_ZERO})
    e, n, h = zero_point
    add_text(msp, f"NP E {e:.3f} N {n:.3f} H {h:.3f}", (0.6 * r, 0.3 * r), 0.6 * TEXT_HEIGHT,
             TextEntityAlignment.BOTTOM_LEFT, layer=LAYER_ZERO)


def save(doc, path):
    try:
        doc.saveas(path)
        return path.name
    except PermissionError:
        return f"FEHLER {path.name} gesperrt (in CAD geöffnet?)"


def write_section(sec, meshes, out_dir, reference=REF_LV95):
    """Schreibt die DXF eines QP und liefert eine Protokollzeile.

    LV95: 2D-Profil (Höhe m ü. M.) und 3D in Landeskoordinaten.
    NP:   nur 2D-Profil, der Nullpunkt des QP liegt auf 0,0.
    """
    if sec.length == 0:
        return f"FEHLER {sec.title}: beide Punkte identisch, nicht exportiert"
    if reference == REF_NP and sec.zero_point is None:
        return f"FEHLER {sec.title}: kein Nullpunkt, nicht exportiert"
    lines = section_lines(sec, meshes)
    shift = sec.shift(reference)
    profile = to_profile(lines, shift)
    mast_stations = (-shift[0], sec.length - shift[0])

    if lines:
        all_s = np.concatenate([s for _, s, _ in profile])
        all_z = np.concatenate([z for *_, z in profile])
        z_min, z_max, s_min = all_z.min(), all_z.max(), min(all_s.min(), mast_stations[0])
    else:
        z_min = z_max = 0.0
        s_min = mast_stations[0]
    z_low, z_top = z_min - MAST_OVERHANG, z_max + MAST_OVERHANG
    statuses = sorted({status for status, _, _ in lines})

    # 2D-Profil: x = Station, y = Höhe (LV95: ab 1. Mast / m ü. M., NP: ab Nullpunkt)
    doc = new_doc(statuses)
    msp = doc.modelspace()
    for status, stations, heights in profile:
        msp.add_lwpolyline(np.column_stack([stations, heights]).tolist(), dxfattribs={"layer": layer_name(status)})
    for station, name in zip(mast_stations, sec.masts):
        msp.add_line((station, z_low), (station, z_top), dxfattribs={"layer": LAYER_MAST})
        add_text(msp, name, (station, z_top + 0.2 * TEXT_HEIGHT))
    add_text(msp, sec.title, (s_min, z_top + 3 * TEXT_HEIGHT), 2 * TEXT_HEIGHT, TextEntityAlignment.BOTTOM_LEFT)

    if reference == REF_NP:
        doc.layers.add(LAYER_ZERO, color=6)
        add_zero_point(msp, sec.zero_point)
        names = [save(doc, out_dir / f"{sec.file_stem}_NP.dxf")]
    else:
        names = [save(doc, out_dir / f"{sec.file_stem}.dxf")]

        # 3D in LV95: Masten an ihrer echten Lage, Texte horizontal und in der Situation lesbar
        doc = new_doc(statuses)
        msp = doc.modelspace()
        for status, pts, _ in lines:
            msp.add_polyline3d(pts.tolist(), dxfattribs={"layer": layer_name(status)})
        for (e, n), name in zip((sec.start, sec.end), sec.masts):
            msp.add_line((e, n, z_low), (e, n, z_top), dxfattribs={"layer": LAYER_MAST})
            add_text(msp, name, (e, n, z_top + 0.2 * TEXT_HEIGHT))
        e, n = sec.origin + s_min * sec.direction
        rotation = math.degrees(math.atan2(sec.direction[1], sec.direction[0]))
        add_text(msp, sec.title, (e, n, z_top), 2 * TEXT_HEIGHT, TextEntityAlignment.BOTTOM_LEFT, rotation)
        names.append(save(doc, out_dir / f"{sec.file_stem}_3D.dxf"))

    if lines:
        info = f"{len(lines)} Linien, Station {all_s.min():.1f} bis {all_s.max():.1f} m"
    else:
        info = "WARNUNG Schnitt trifft kein Gelände"
    return f"{sec.title}: {info} -> {', '.join(names)}"


def export_sections(sections, meshes, out_dir, reference=REF_LV95):
    """Schreibt die DXF mehrerer QP nach out_dir und liefert die Protokollzeilen."""
    stems = [s.file_stem for s in sections]
    log = [f"WARNUNG {stem} kommt mehrfach vor, Datei wird überschrieben"
           for stem in sorted({s for s in stems if stems.count(s) > 1})]
    out_dir.mkdir(parents=True, exist_ok=True)
    return log + [write_section(sec, meshes, out_dir, reference) for sec in sections]
