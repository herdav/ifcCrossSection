"""IFC-Geländemodell lesen: Georeferenz, Triangulierung, Projektstatus."""

import math
import multiprocessing

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement
import numpy as np

from .config import GEOMETRY_LIBRARY, OFFSET, STATUS_PROP, STATUS_PSET, TERRAIN_TYPES
from .model import DataError, Mesh


def georef(model):
    """Liefert eine Funktion, die lokale Modellkoordinaten nach LV95/LN02 umrechnet."""
    if OFFSET is not None:
        offset = np.array(OFFSET, float)
        return lambda v: v + offset

    for mc in model.by_type("IfcMapConversion"):
        a, o = mc.XAxisAbscissa or 1.0, mc.XAxisOrdinate or 0.0
        cos, sin = a / math.hypot(a, o), o / math.hypot(a, o)
        k = mc.Scale or 1.0
        origin = np.array([mc.Eastings, mc.Northings, mc.OrthogonalHeight], float)

        def to_lv95(v):
            x, y, z = (k * v).T
            return origin + np.column_stack([cos * x - sin * y, sin * x + cos * y, z])

        return to_lv95

    # SBB-Konvention: Projektnullpunkt trägt die Landeskoordinaten als Eigenschaften
    for el in model.by_type("IfcBuildingElementProxy"):
        psets = ifcopenshell.util.element.get_psets(el)
        if "Projektnullpunkt" not in (el.Name, psets.get(STATUS_PSET, {}).get("ObjectTypeName")):
            continue
        for props in psets.values():
            if all(f"Koordinate {c}" in props for c in "ENZ"):
                local = ifcopenshell.util.placement.get_local_placement(el.ObjectPlacement)[:3, 3]
                offset = np.array([float(props[f"Koordinate {c}"]) for c in "ENZ"]) - local
                return lambda v: v + offset

    raise DataError("Keine Georeferenz im IFC gefunden (IfcMapConversion / Projektnullpunkt). "
                    "Bitte OFFSET in core/config.py setzen.")


def terrain_elements(model):
    for ifc_type in TERRAIN_TYPES:
        try:
            yield from model.by_type(ifc_type)
        except RuntimeError:  # Klasse existiert im Schema der Datei nicht
            pass


def project_status(el):
    value = ifcopenshell.util.element.get_psets(el).get(STATUS_PSET, {}).get(STATUS_PROP)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return str(value or "Unbekannt")


def clean_mesh(verts, faces):
    """Doppelte Punkte (z. B. an Kachelgrenzen) verschweissen und Dreiecke ohne Fläche
    entfernen, damit die Schnittlinien sauber durchlaufen."""
    verts, inverse = np.unique(np.round(verts, 4), axis=0, return_inverse=True)
    faces = inverse.reshape(-1)[faces]
    a, b, c = (verts[faces[:, k]] for k in range(3))
    return verts, faces[np.linalg.norm(np.cross(b - a, c - a), axis=1) > 1e-8]


def load_meshes(ifc_path):
    model = ifcopenshell.open(str(ifc_path))
    elements = [el for el in terrain_elements(model) if el.Representation]
    if not elements:
        return []
    to_lv95 = georef(model)
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    iterator = ifcopenshell.geom.iterator(
        settings, model, multiprocessing.cpu_count(), include=elements, geometry_library=GEOMETRY_LIBRARY)

    meshes = []
    if not iterator.initialize():
        return meshes
    while True:
        shape = iterator.get()
        faces = np.array(shape.geometry.faces, dtype=np.int64).reshape(-1, 3)
        if len(faces):
            verts = to_lv95(np.array(shape.geometry.verts, dtype=float).reshape(-1, 3))
            meshes.append(Mesh(project_status(model.by_id(shape.id)), *clean_mesh(verts, faces)))
        if not iterator.next():
            return meshes
