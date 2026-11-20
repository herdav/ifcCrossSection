"""Geländedaten nach Dateityp laden: IFC und LandXML (Flächen), XYZ (Raster), DXF (Bruchkanten)."""

from .breakline_reader import load_breaklines
from .grid_reader import load_grid
from .ifc_reader import load_meshes
from .landxml_reader import load_landxml
from .model import Breakline, Grid, Mesh

TERRAIN_SUFFIXES = (".ifc", ".xml", ".xyz", ".zip", ".dxf")


def load_terrain(paths):
    """Liefert die Geländedaten aller Dateien: Flächen zuerst (in Dateireihenfolge), dann Raster, dann Bruchkanten."""
    meshes, grid_paths, breaklines = [], [], []
    for path in paths:
        suffix = path.suffix.lower()
        if suffix == ".ifc":
            meshes += load_meshes(path)
        elif suffix == ".xml":
            meshes += load_landxml(path)
        elif suffix in (".xyz", ".zip"):
            grid_paths.append(path)
        elif suffix == ".dxf":
            breaklines += load_breaklines(path)
    grids = [load_grid(grid_paths)] if grid_paths else []
    return meshes + grids + breaklines


def describe(terrain):
    """Kurzbeschreibung für das Protokoll."""
    meshes = [t for t in terrain if isinstance(t, Mesh)]
    grids = [t for t in terrain if isinstance(t, Grid)]
    lines = [t for t in terrain if isinstance(t, Breakline)]
    triangles = f"{sum(len(m.faces) for m in meshes):,}".replace(",", "'")
    parts = [f"{len(meshes)} Geländeflächen, {triangles} Dreiecke"]
    for g in grids:
        parts.append(f"Raster {g.status} {g.z.shape[1]} x {g.z.shape[0]} Punkte à {g.step:g} m")
    if lines:
        parts.append(f"{len(lines)} Bruchkanten")
    return ", ".join(parts)
