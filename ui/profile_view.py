"""Querprofil des aktiven QP (QPainter) mit Raster, Masten, NP und Mausposition."""

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from core.config import MAST_OVERHANG, RAIL_LAYER, REF_LV95, REF_NP, ZH_NONE, ZH_RAILS
from core.cutting import reference_shift, to_profile
from core.model import CutSettings

from .theme import BG, BREAKLINE_COLOR, GRID, LINE_COLORS, MAST_COLOR, OTHER_COLOR, RAIL_COLOR, ZERO_COLOR


def nice_step(min_step):
    exp = 10 ** math.floor(math.log10(min_step))
    return next(m * exp for m in (1, 2, 5, 10) if m * exp >= min_step)


def ticks(lo, hi, min_step):
    step = nice_step(min_step)
    return np.arange(math.ceil(lo / step) * step, hi + step * 1e-6, step), step


class ProfileView(QWidget):
    """Querprofil des aktiven QP mit Überhöhung.

    Bezug LV95: x = Station ab Punkt 1, y = Höhe m ü. M.  Bezug NP: Nullpunkt auf 0,0 (wie DXF).
    Schienen als Dreieck, übrige Bruchkanten als Kreuz mit Code.
    """

    hovered = Signal(str)

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setMinimumHeight(180)
        self.section = None
        self.profile = []  # (Status, Stationen, Höhen) im gewählten Bezug
        self.marks = []  # (Code, Station, Höhe) im gewählten Bezug
        self.reference = REF_LV95
        self.settings = CutSettings()
        self.relative = False
        self.no_rails = False  # NP-Höhe aus den Schienen gewählt, aber keine am NP: Kote der Tabelle
        self._shift = (0.0, 0.0)
        self.exaggeration = 1.0
        self._transform = None  # (s0, z1, kx, kz, x0, y0) für die Mausposition

    def set_profile(self, section, lines, reference=REF_LV95, settings=None, marks=()):
        self.section = section
        self.reference = reference
        self.settings = settings or CutSettings()
        self.relative = section is not None and reference == REF_NP and section.zero_point is not None
        shift = reference_shift(section, reference, self.settings, marks) if section else (0.0, 0.0)
        self.no_rails = shift[1] is None
        if self.no_rails:
            shift = (shift[0], section.zero_point[2])
        self._shift = shift
        self.profile = to_profile(lines, shift)
        self.marks = [(code, s - shift[0], p[2] - shift[1]) for code, p, s in marks]
        self.update()

    def shift(self):
        return self._shift

    def zero_height(self):
        """Höhe des NP-Kreuzes im angezeigten Bezug."""
        if self.relative and self.settings.zero_height != ZH_NONE:
            return 0.0
        return self.section.zero_point[2] - self._shift[1]

    def set_exaggeration(self, value):
        self.exaggeration = value
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(BG))
        self._transform = None
        if self.section is None or self.section.length == 0:
            p.setPen(QColor("#808080"))
            p.drawText(self.rect(), Qt.AlignCenter, "Kein Querprofil")
            return

        s_shift, z_shift = self.shift()
        masts = [(station - s_shift, label) for station, _, label, _, _ in self.section.mast_points()]
        zero = None
        if self.section.zero_point is not None:
            zero = (self.section.zero_station - s_shift, self.zero_height())
        s_all = np.concatenate([s for _, s, _ in self.profile] + [np.array([m for m, _ in masts] or [-s_shift])])
        z_all = np.concatenate([z for *_, z in self.profile]) if self.profile else np.array([0.0])
        if self.marks:
            z_all = np.r_[z_all, [z for *_, z in self.marks]]
        if zero:
            s_all, z_all = np.r_[s_all, zero[0]], np.r_[z_all, zero[1]]
        s0, s1 = s_all.min(), s_all.max()
        pad = 0.02 * (s1 - s0)
        s0, s1 = s0 - pad, s1 + pad
        z0, z1 = z_all.min() - MAST_OVERHANG, z_all.max() + MAST_OVERHANG

        left, right, top, bottom = 64, 16, 48, 28
        w, h = max(self.width() - left - right, 10), max(self.height() - top - bottom, 10)
        k = min(w / (s1 - s0), h / ((z1 - z0) * self.exaggeration))
        kx, kz = k, k * self.exaggeration
        x0 = left + (w - (s1 - s0) * kx) / 2
        y0 = top + (h - (z1 - z0) * kz) / 2
        self._transform = (s0, z1, kx, kz, x0, y0)

        def pt(s, z):
            return QPointF(x0 + (s - s0) * kx, y0 + (z1 - z) * kz)

        font = p.font()
        font.setPointSizeF(8)
        p.setFont(font)
        heights, z_step = ticks(z0, z1, 28 / kz)
        for z in heights:
            p.setPen(QPen(QColor(GRID), 1))
            p.drawLine(pt(s0, z), pt(s1, z))
            p.setPen(QColor("#9a9a9a"))
            p.drawText(QRectF(pt(s0, z).x() - 60, pt(s0, z).y() - 8, 54, 16), Qt.AlignRight | Qt.AlignVCenter,
                       f"{z:.{0 if z_step >= 1 else 1}f}")
        for s in ticks(s0, s1, 60 / kx)[0]:
            p.setPen(QPen(QColor(GRID), 1))
            p.drawLine(pt(s, z0), pt(s, z1))
            p.setPen(QColor("#9a9a9a"))
            p.drawText(QRectF(pt(s, z0).x() - 30, pt(s, z0).y() + 4, 60, 16), Qt.AlignCenter, f"{s:.0f}")

        for status, stations, heights in self.profile:
            p.setPen(QPen(QColor(LINE_COLORS.get(status, OTHER_COLOR)), 2))
            p.drawPolyline(QPolygonF([pt(s, z) for s, z in zip(stations, heights)]))

        for station, name in masts:
            p.setPen(QPen(QColor(MAST_COLOR), 1, Qt.DashLine))
            p.drawLine(pt(station, z0), pt(station, z1))
            p.setPen(QColor(MAST_COLOR))
            p.drawText(QRectF(pt(station, z1).x() - 40, pt(station, z1).y() - 18, 80, 16), Qt.AlignCenter, name)

        for code, station, height in self.marks:
            c = pt(station, height)
            if code == RAIL_LAYER:
                p.setPen(QPen(QColor(RAIL_COLOR), 1.5))
                p.drawPolygon(QPolygonF([c, c + QPointF(-5, -8), c + QPointF(5, -8)]))
            else:
                p.setPen(QPen(QColor(BREAKLINE_COLOR), 1.5))
                p.drawLine(c + QPointF(-4, -4), c + QPointF(4, 4))
                p.drawLine(c + QPointF(-4, 4), c + QPointF(4, -4))
                p.save()
                p.translate(c + QPointF(3, -6))
                p.rotate(-60)
                p.drawText(QPointF(0, 0), code)
                p.restore()

        if zero:
            c = pt(*zero)
            p.setPen(QPen(QColor(ZERO_COLOR), 2))
            p.drawLine(c + QPointF(-7, 0), c + QPointF(7, 0))
            p.drawLine(c + QPointF(0, -7), c + QPointF(0, 7))
            p.drawText(QRectF(c.x() + 6, c.y() - 20, 40, 16), Qt.AlignLeft | Qt.AlignVCenter, "NP")

        font.setPointSizeF(10)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("white"))
        p.drawText(QRectF(left, 6, w, 20), Qt.AlignLeft | Qt.AlignVCenter, self.section.title)
        font.setBold(False)
        font.setPointSizeF(8)
        p.setFont(font)
        p.setPen(QColor("#9a9a9a"))
        if self.relative and self.no_rails:
            axes = "Bezug NP: keine Schienen am NP, Höhe ab Kote Tabelle [m]"
        elif self.relative and self.settings.zero_height == ZH_NONE:
            axes = "Bezug NP: Station ab NP [m] / Höhe [m ü. M.]"
        elif self.relative:
            height = "bestehender SOK" if self.settings.zero_height == ZH_RAILS else "NP"
            axes = f"Bezug NP: Station ab NP [m] / Höhe ab {height} [m]"
        elif self.reference == REF_NP:
            axes = "Kein NP, Anzeige LV95: Station ab Punkt 1 [m] / Höhe [m ü. M.]"
        else:
            axes = "Bezug LV95: Station ab Punkt 1 [m] / Höhe [m ü. M.]"
        p.drawText(QRectF(left, 6, w, 20), Qt.AlignRight | Qt.AlignVCenter,
                   f"{axes}, Überhöhung {self.exaggeration:g}x")

    def mouseMoveEvent(self, event):
        if not self._transform:
            return
        s0, z1, kx, kz, x0, y0 = self._transform
        s = s0 + (event.position().x() - x0) / kx
        z = z1 - (event.position().y() - y0) / kz
        ground = [np.interp(s, st, hz) for _, st, hz in self.profile if st[0] <= s <= st[-1]]
        unit = "m ab NP" if self.relative and self.settings.zero_height != ZH_NONE else "m ü. M."
        text = f"Station {s:.2f} m, Höhe {z:.2f} {unit}"
        if ground:
            text += f", Gelände {max(ground):.2f} {unit}"
        self.hovered.emit(text)
