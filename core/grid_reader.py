"""Höhenraster aus XYZ-Dateien (z. B. swissALTI3D, Kacheln 1 x 1 km, 0.5 m).

Eine Zeile «E N H», optional mit Kopfzeile. Auch als ZIP mit einer XYZ-Datei.
Mehrere Kacheln mit gleicher Maschenweite werden zu einem Raster zusammengesetzt.
"""

import io
import zipfile

import numpy as np

from .config import GRID_STATUS
from .model import DataError, Grid, Mesh


def read_xyz(path):
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith((".xyz", ".txt", ".csv"))]
            if not names:
                raise DataError(f"{path.name}: keine XYZ-Datei im ZIP")
            text = zf.read(names[0]).decode("ascii", errors="ignore")
    else:
        text = path.read_text(encoding="ascii", errors="ignore")
    first, _, rest = text.partition("\n")
    if any(c.isalpha() for c in first):  # Kopfzeile «X Y Z»
        text = rest
    values = np.array(text.replace(",", " ").replace(";", " ").split(), float)
    if not len(values) or len(values) % 3:
        raise DataError(f"{path.name}: kein XYZ-Raster (je Zeile E N H erwartet)")
    return values.reshape(-1, 3)


def load_grid(paths, status=GRID_STATUS):
    """Liest alle Kacheln und setzt sie zu einem Raster zusammen (fehlende Zellen NaN)."""
    points = np.vstack([read_xyz(p) for p in paths])
    xs, ys = np.unique(points[:, 0]), np.unique(points[:, 1])
    step = float(np.min(np.diff(xs))) if len(xs) > 1 else 1.0
    x0, y0 = xs[0], ys[0]
    col = np.rint((points[:, 0] - x0) / step).astype(int)
    row = np.rint((points[:, 1] - y0) / step).astype(int)
    if np.abs(points[:, 0] - (x0 + col * step)).max() > step * 0.01:
        raise DataError("Raster mit unterschiedlicher Maschenweite oder Lage, nicht zusammensetzbar")
    z = np.full((row.max() + 1, col.max() + 1), np.nan, np.float32)
    z[row, col] = points[:, 2]
    return Grid(status, float(x0), float(y0), step, z)


def grid_mesh(grid, bbox):
    """Trianguliert die Rasterzellen in bbox = (E min, N min, E max, N max), zwei Dreiecke je Zelle."""
    e0, n0, e1, n1 = bbox
    ny, nx = grid.z.shape
    c0, c1 = max(int(np.floor((e0 - grid.x0) / grid.step)), 0), min(int(np.ceil((e1 - grid.x0) / grid.step)), nx - 1)
    r0, r1 = max(int(np.floor((n0 - grid.y0) / grid.step)), 0), min(int(np.ceil((n1 - grid.y0) / grid.step)), ny - 1)
    if c1 <= c0 or r1 <= r0:
        return None
    z = grid.z[r0:r1 + 1, c0:c1 + 1].astype(float)
    rows, cols = np.mgrid[r0:r1 + 1, c0:c1 + 1]
    verts = np.column_stack([grid.x0 + cols.ravel() * grid.step, grid.y0 + rows.ravel() * grid.step, z.ravel()])
    idx = np.arange(len(verts)).reshape(z.shape)
    a, b, c, d = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()
    faces = np.vstack([np.column_stack([a, b, c]), np.column_stack([a, c, d])])
    faces = faces[~np.isnan(verts[faces, 2]).any(1)]
    if not len(faces):
        return None
    used, faces = np.unique(faces, return_inverse=True)
    return Mesh(grid.status, verts[used], faces.reshape(-1, 3))


def grid_patches(grid, bboxes):
    """Ein Mesh aus den Rasterausschnitten in bboxes (für die 3D-Ansicht), None wenn leer."""
    verts, faces, count = [], [], 0
    for bbox in bboxes:
        mesh = grid_mesh(grid, bbox)
        if mesh is not None:
            verts.append(mesh.verts)
            faces.append(mesh.faces + count)
            count += len(mesh.verts)
    return Mesh(grid.status, np.vstack(verts), np.vstack(faces)) if verts else None


def section_bbox(origin, direction, s0, s1, buffer):
    pts = np.array([origin + s0 * direction, origin + s1 * direction])
    return (*(pts.min(0) - buffer), *(pts.max(0) + buffer))
