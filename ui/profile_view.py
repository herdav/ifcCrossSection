"""Querprofil des aktiven QP (QPainter) mit Raster, Masten, NP und Mausposition."""

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from core.config import MAST_OVERHANG, REF_LV95, REF_NP
from core.cutting import to_profile

from .theme import BG, GRID, LINE_COLORS, MAST_COLOR, OTHER_COLOR, ZERO_COLOR


def nice_step(min_step):
    exp = 10 ** math.floor(math.log10(min_step))
    return next(m * exp for m in (1, 2, 5, 10) if m * exp >= min_step)


def ticks(lo, hi, min_step):
    step = nice_step(min_step)
    return np.arange(math.ceil(lo / step) * step, hi + step * 1e-6, step), step


class ProfileView(QWidget):
    """Querprofil des aktiven QP mit Überhöhung.

    Bezug LV95: x = Station ab 1. Mast, y = Höhe m ü. M.  Bezug NP: Nullpunkt auf 0,0 (wie DXF).
    """

    hovered = Signal(str)

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setMinimumHeight(180)
        self.section = None
        self.profile = []  # (Status, Stationen, Höhen) im gewählten Bezug
        self.reference = REF_LV95
        self.relative = False
        self.exaggeration = 1.0
        self._transform = None  # (s0, z1, kx, kz, x0, y0) für die Mausposition

    def set_profile(self, section, lines, reference=REF_LV95):
        self.section = section
        self.reference = reference
        self.relative = section is not None and reference == REF_NP and section.zero_point is not None
        self.profile = to_profile(lines, self.shift())
        self.update()

    def shift(self):
        return self.section.shift(self.reference) if self.section else (0.0, 0.0)

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
        masts = [(station - s_shift, name) for station, name in zip((0.0, self.section.length), self.section.masts)]
        zero = None
        if self.section.zero_point is not None:
            zero = (self.section.zero_station - s_shift, self.section.zero_point[2] - z_shift)
        s_all = np.concatenate([s for _, s, _ in self.profile] + [np.array([m for m, _ in masts])])
        z_all = np.concatenate([z for *_, z in self.profile]) if self.profile else np.array([0.0])
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
        if self.relative:
            axes = "Bezug NP: Station ab NP [m] / Höhe ab NP [m]"
        elif self.reference == REF_NP:
            axes = "Kein NP, Anzeige LV95: Station ab Mast 1 [m] / Höhe [m ü. M.]"
        else:
            axes = "Bezug LV95: Station ab Mast 1 [m] / Höhe [m ü. M.]"
        p.drawText(QRectF(left, 6, w, 20), Qt.AlignRight | Qt.AlignVCenter,
                   f"{axes}, Überhöhung {self.exaggeration:g}x")

    def mouseMoveEvent(self, event):
        if not self._transform:
            return
        s0, z1, kx, kz, x0, y0 = self._transform
        s = s0 + (event.position().x() - x0) / kx
        z = z1 - (event.position().y() - y0) / kz
        ground = [np.interp(s, st, hz) for _, st, hz in self.profile if st[0] <= s <= st[-1]]
        unit = "m ab NP" if self.relative else "m ü. M."
        text = f"Station {s:.2f} m, Höhe {z:.2f} {unit}"
        if ground:
            text += f", Gelände {max(ground):.2f} {unit}"
        self.hovered.emit(text)
