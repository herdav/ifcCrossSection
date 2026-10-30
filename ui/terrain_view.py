"""3D-Vorschau (pyvistaqt): Gelände je Status, Schnittspuren aller QP, aktiver QP mit Schnittebene."""

import numpy as np
import pyvista as pv
from PySide6.QtWidgets import QVBoxLayout, QWidget
from pyvistaqt import QtInteractor

from core.config import MAST_OVERHANG

from .theme import ACTIVE_COLOR, BG, MAST_COLOR, OTHER_COLOR, TERRAIN_COLORS, TRACE_COLOR, ZERO_COLOR

TRACE_LIFT = 0.15  # m, Schnittspuren knapp über dem Gelände zeichnen


def polyline_mesh(point_arrays):
    """Mehrere Linienzüge als ein PolyData (ein Actor statt vieler)."""
    points = np.vstack(point_arrays)
    cells, offset = [], 0
    for pts in point_arrays:
        cells.append(np.r_[len(pts), np.arange(offset, offset + len(pts))])
        offset += len(pts)
    return pv.PolyData(points, lines=np.concatenate(cells))


class TerrainView(QWidget):
    """3D-Vorschau: Gelände je Status, Schnittspuren aller QP, aktiver QP mit Schnittebene."""

    ACTIVE_ACTORS = ("active_plane", "active_lines", "active_masts", "active_labels", "active_zero")

    def __init__(self):
        super().__init__()
        self.plotter = QtInteractor(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plotter.interactor)
        self.plotter.set_background(BG)
        self.plotter.add_axes(color="white")
        self.plotter.enable_anti_aliasing("fxaa")
        self.origin = np.zeros(3)
        self.exaggeration = 1.0
        self.terrain = []  # (PolyData, Punkte LV95)

    def view(self, pts):
        """LV95 -> Anzeige: um Ursprung verschoben (Genauigkeit in VTK) und überhöht."""
        v = np.asarray(pts, float) - self.origin
        v[..., 2] *= self.exaggeration
        return v

    def set_meshes(self, meshes):
        self.plotter.clear_actors()
        self.terrain = []
        if meshes:
            self.origin = np.floor(np.vstack([m.verts for m in meshes]).min(0))
        for i, mesh in enumerate(meshes):
            faces = np.hstack([np.full((len(mesh.faces), 1), 3), mesh.faces]).ravel()
            poly = pv.PolyData(self.view(mesh.verts), faces)
            self.plotter.add_mesh(poly, color=TERRAIN_COLORS.get(mesh.status, OTHER_COLOR), name=f"terrain{i}")
            self.terrain.append((poly, mesh.verts))
        self.plotter.view_isometric()
        self.plotter.reset_camera()

    def set_exaggeration(self, value):
        self.exaggeration = value
        for poly, verts in self.terrain:
            poly.points = self.view(verts)

    def set_traces(self, all_lines):
        lifted = [pts + [0, 0, TRACE_LIFT] for lines in all_lines for _, pts, _ in lines]
        if lifted:
            self.plotter.add_mesh(polyline_mesh([self.view(p) for p in lifted]), color=TRACE_COLOR,
                                  line_width=2, lighting=False, name="traces")
        else:
            self.plotter.remove_actor("traces")

    def set_active(self, sec, lines):
        if sec is None or sec.length == 0:
            for name in self.ACTIVE_ACTORS:
                self.plotter.remove_actor(name)
            self.plotter.render()
            return

        s0, s1, z0, z1 = self._extent(sec, lines)
        a, b = (sec.origin + s * sec.direction for s in (s0, s1))
        quad = np.array([[*a, z0], [*b, z0], [*b, z1], [*a, z1]])
        self.plotter.add_mesh(pv.PolyData(self.view(quad), faces=[4, 0, 1, 2, 3]), color=ACTIVE_COLOR,
                              opacity=0.18, lighting=False, name="active_plane")
        if lines:
            self.plotter.add_mesh(polyline_mesh([self.view(pts + [0, 0, TRACE_LIFT]) for _, pts, _ in lines]),
                                  color=ACTIVE_COLOR, line_width=5, render_lines_as_tubes=True,
                                  lighting=False, name="active_lines")
        else:
            self.plotter.remove_actor("active_lines")
        masts = [np.array([[*p, z0], [*p, z1]]) for p in (sec.start, sec.end)]
        self.plotter.add_mesh(polyline_mesh([self.view(m) for m in masts]), color=MAST_COLOR,
                              line_width=3, lighting=False, name="active_masts")
        label_points, labels = [[*sec.start, z1], [*sec.end, z1], [*a, z1]], [*sec.masts, sec.title]
        if sec.zero_point is not None:
            self.plotter.add_mesh(pv.PolyData(self.view(sec.zero_point[None, :])), color=ZERO_COLOR, point_size=14,
                                  render_points_as_spheres=True, lighting=False, name="active_zero")
            label_points.append(sec.zero_point)
            labels.append("NP")
        else:
            self.plotter.remove_actor("active_zero")
        self.plotter.add_point_labels(
            self.view(np.array(label_points)), labels, name="active_labels", font_size=14,
            text_color="white", shape_color=BG, shape_opacity=0.6, show_points=False, always_visible=True)
        self.plotter.render()

    def focus(self, sec, lines):
        """Kamera seitlich auf den QP: 1. Punkt links, wie im Querprofil."""
        if sec is None or sec.length == 0:
            return
        s0, s1, z0, z1 = self._extent(sec, lines)
        normal = np.array([-sec.direction[1], sec.direction[0]])
        centre = sec.origin + (s0 + s1) / 2 * sec.direction
        focal = self.view([*centre, (z0 + z1) / 2])
        width = max(s1 - s0, 20.0)
        position = focal + np.r_[-normal * width * 1.1, width * 0.45]
        self.plotter.camera_position = [position, focal, (0, 0, 1)]
        self.plotter.render()

    def _extent(self, sec, lines):
        stations = np.concatenate([s for *_, s in lines] + [np.array([0.0, sec.length])])
        heights = np.concatenate([pts[:, 2] for _, pts, _ in lines]) if lines else np.array([self.origin[2]])
        return (stations.min(), stations.max(), heights.min() - MAST_OVERHANG, heights.max() + MAST_OVERHANG)
