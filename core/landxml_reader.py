"""Geländeflächen (TIN) aus LandXML lesen.

Ein Punkt steht als «Nord Ost Höhe», Nord zuerst. Ein Dreieck sind drei Punkt-IDs.
"""

import xml.etree.ElementTree as ET

import numpy as np

from .config import LANDXML_STATUS, LANDXML_WELD_DECIMALS
from .ifc_reader import clean_mesh
from .model import DataError, Mesh


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def children(el, name):
    return [c for c in el if local_name(c.tag) == name]


def load_landxml(path, status=LANDXML_STATUS):
    """Liefert ein Mesh pro Surface (LV95 / LN02, Punkte verschweisst)."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise DataError(f"{path.name}: kein gültiges XML ({exc})") from None
    meshes = []
    for surface in root.iter():
        if local_name(surface.tag) != "Surface":
            continue
        for definition in children(surface, "Definition"):
            ids, points, faces = {}, [], []
            for pnts in children(definition, "Pnts"):
                for p in children(pnts, "P"):
                    n, e, z = (float(v) for v in p.text.split()[:3])
                    ids[p.get("id")] = len(points)
                    points.append((e, n, z))
            for fs in children(definition, "Faces"):
                for f in children(fs, "F"):
                    if f.get("i") == "1":  # unsichtbares Dreieck (Loch)
                        continue
                    try:
                        faces.append([ids[k] for k in f.text.split()[:3]])
                    except KeyError as exc:
                        raise DataError(f"{path.name}: Dreieck verweist auf fehlenden Punkt {exc}") from None
            if faces:
                verts, tris = clean_mesh(np.array(points, float), np.array(faces, np.int64), LANDXML_WELD_DECIMALS)
                meshes.append(Mesh(status, verts, tris))
    if not meshes:
        raise DataError(f"{path.name}: keine Surface mit Dreiecken gefunden")
    return meshes
