"""Tests des Kerns mit erfundenen Daten (keine Projektdaten im Repo).

Aufruf:  python -m unittest discover tests
Gleis: gerade nach Süden (km steigt, N fällt), Gelände eine schiefe Ebene H = 400 + 0.1 * (E - E0).
"""

import tempfile
import unittest
from pathlib import Path

import ezdxf
import numpy as np
import openpyxl

from core.config import RAIL_LAYER, REF_NP, ZH_NONE, ZH_RAILS
from core.cutting import clip_line, reference_shift, section_lines, section_marks, terrain_height
from core.dxf_writer import write_section
from core.excel_reader import read_sections
from core.grid_reader import load_grid
from core.landxml_reader import load_landxml
from core.model import Breakline, CutSettings, Mesh
from core.project import Project
from core.terrain import load_terrain

E0, N0 = 2600000.0, 1200000.0  # erfunden


def height(e):
    return 400 + 0.1 * (e - E0)


def write_landxml(path):
    """Ebene von E0 - 20 bis E0 + 20, N0 - 200 bis N0 + 20; Punkte «N E H», ein doppelter Punkt."""
    pts, faces = [], []
    es, ns = np.arange(-20, 21, 10.0), np.arange(-200, 21, 10.0)
    for n in ns:
        for e in es:
            pts.append((N0 + n, E0 + e, height(E0 + e)))
    w = len(es)
    for r in range(len(ns) - 1):
        for c in range(w - 1):
            a = r * w + c + 1
            faces += [(a, a + 1, a + w + 1), (a, a + w + 1, a + w)]
    pts.append(pts[0])  # doppelt, wird verschweisst
    faces.append((1, len(pts), 2))  # ohne Fläche
    xml = ['<?xml version="1.0" encoding="ISO-8859-1"?>',
           '<LandXML xmlns="http://www.landxml.org/schema/LandXML-1.0" version="1.0"><Surfaces>',
           '<Surface name="Test"><Definition surfType="TIN"><Pnts>']
    xml += [f'<P id="{i}">{n:.3f} {e:.3f} {z:.3f}</P>' for i, (n, e, z) in enumerate(pts, 1)]
    xml.append("</Pnts><Faces>")
    xml += [f"<F>{a} {b} {c}</F>" for a, b, c in faces]
    xml.append("</Faces></Definition></Surface></Surfaces></LandXML>")
    path.write_text("\n".join(xml), encoding="iso-8859-1")


def foot(km):
    return E0, N0 - (km - 1.0) * 1000


def write_foundation_list(path):
    """Fundamentliste: Masten alle 20 m, rechts (Westen) bzw. links (Osten), ein Paar, ein Anker,
    eine Zeile mit vertauschtem Fusspunkt, eine doppelte Nummer."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "LISTE"
    for r in range(1, 18):
        ws.cell(r, 1, f"Kopf {r}")
    rows = []
    for k in range(8):
        km = 1.0 + k * 0.02
        side = -1 if k % 2 == 0 else 1  # -1: Westen = rechts in Richtung steigender km (Süden)
        e, n = foot(km)
        rows.append((km + 1e-12, str(k + 1), "DP26", "Gl 1", "3.000", e, n, f"{e + side * 3:.3f}", f"{n:.3f}",
                     height(e) + 0.5, "DP2a/2.0"))
    e, n = foot(1.06)
    rows.append((1.06, "20", "DP26", "Gl 1", 3.0, e, n, f"{e - 3:.3f}", f"{n:.3f}", 405.0, "DP2a/2.7"))  # Paar zu 4
    rows.append((1.062, "A zu 4", None, "Gl 1", 3.0, e, n, f"{e + 3:.3f}", f"{n - 2:.3f}", 405.0, None))
    e, n = foot(1.16)
    rows.append((1.16, "9", "DP26", "Gl 1", 3.0, n, e, f"{e - 3:.3f}", f"{n:.3f}", 400.5, "DP2a/2.0"))  # H, I vertauscht
    e, n = foot(1.18)
    rows.append((1.18, "1", "DP22", "Gl 1", 3.0, e, n, f"{e - 3:.3f}", f"{n:.3f}", 400.5, "DP1a/1.8"))  # Nummer doppelt
    for r, (km, nr, typ, gl, a, fe, fn, me, mn, kote, fund) in enumerate(rows, 18):
        for col, value in zip("ABCDFHILMNY", (km, nr, typ, gl, a, fe, fn, me, mn, kote, fund)):
            ws[f"{col}{r}"] = value
    wb.save(path)


def rails():
    top = height(E0) - 0.2
    return [Breakline(RAIL_LAYER, np.array([[E0 + d, N0 + 50, top], [E0 + d, N0 - 250, top]])) for d in (-0.5, 0.5)]


class CoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        write_landxml(self.dir / "gelaende.xml")
        write_foundation_list(self.dir / "liste.xlsm")
        self.terrain = load_landxml(self.dir / "gelaende.xml") + rails()
        self.sections, self.messages = read_sections(self.dir / "liste.xlsm")

    def tearDown(self):
        self.tmp.cleanup()

    def section(self, km):
        return next(s for s in self.sections if abs(s.km - km) < 1e-9)

    def test_landxml(self):
        mesh = self.terrain[0]
        self.assertEqual(len(mesh.verts), 5 * 23)
        self.assertEqual(len(mesh.faces), 2 * 4 * 22)  # Dreieck ohne Fläche entfernt
        self.assertAlmostEqual(mesh.verts[:, 0].min(), E0 - 20)  # Ost aus der zweiten Zahl
        self.assertAlmostEqual(mesh.verts[:, 1].max(), N0 + 20)

    def test_foundation_list(self):
        self.assertIn("12 Zeilen: 11 Masten, 1 Anker oder Druckstützen, 10 Querprofile", self.messages)
        pair = self.section(1.06)
        self.assertEqual(pair.qp, "4+20")
        self.assertTrue(any("Mastnummern mehrfach" in m and "1" in m for m in self.messages))
        warned = {s.qp for s in self.sections if s.warnings}
        self.assertEqual(warned, {"9"})

    def test_view_direction(self):
        """Mast rechts des Gleises in km-Richtung (Westen) steht bei positiver Station ab NP."""
        for sec in self.sections:
            if sec.warnings:
                continue
            for station, name, _, point, _ in sec.mast_points():
                west = point[0] < sec.zero_point[0]
                self.assertEqual(station - sec.zero_station > 0, west, f"{sec.title} Mast {name}")

    def test_cut_and_rails(self):
        sec = self.section(1.02)
        settings = CutSettings(half_length=10.0)
        lines = section_lines(sec, self.terrain, settings)
        stations = np.concatenate([s for *_, s in lines]) - sec.zero_station
        self.assertAlmostEqual(stations.min(), -10.0)
        self.assertAlmostEqual(stations.max(), 10.0)
        mast_station = sec.mast_points()[0][0]
        e = sec.mast_points()[0][3][0]
        self.assertAlmostEqual(terrain_height(lines, mast_station)[1], height(e), places=6)
        marks = section_marks(sec, self.terrain, settings)
        self.assertEqual(sorted(round(s - sec.zero_station, 3) for _, _, s in marks), [-0.5, 0.5])
        self.assertAlmostEqual(reference_shift(sec, REF_NP, CutSettings(zero_height=ZH_RAILS), marks)[1],
                               height(E0) - 0.2)
        self.assertEqual(reference_shift(sec, REF_NP, CutSettings(zero_height=ZH_NONE), marks)[1], 0.0)

    def test_clip_line(self):
        pts = np.array([[0, 0, 0], [10, 0, 1], [20, 0, 2]], float)
        parts = clip_line(pts, pts[:, 0], 5, 15)
        self.assertEqual(len(parts), 1)
        np.testing.assert_allclose(parts[0][:, 0], [5, 10, 15])
        self.assertEqual(clip_line(pts, pts[:, 0], 30, 40), [])

    def test_grid(self):
        lines = []
        for e in np.arange(-30, 30.1, 0.5):
            for n in np.arange(-60, 30.1, 0.5):
                lines.append(f"{E0 + e:.2f} {N0 + n:.2f} {height(E0 + e):.3f}")
        (self.dir / "raster.xyz").write_text("X Y Z\n" + "\n".join(lines), encoding="ascii")
        grid = load_grid([self.dir / "raster.xyz"])
        self.assertEqual(grid.z.shape, (181, 121))
        sec = self.section(1.02)
        cut = section_lines(sec, [grid], CutSettings(half_length=20.0))
        mast_station, _, _, point, _ = sec.mast_points()[0]
        self.assertAlmostEqual(terrain_height(cut, mast_station)[1], height(point[0]), places=4)

    def test_dxf_np(self):
        sec = self.section(1.02)
        log = write_section(sec, self.terrain, self.dir, REF_NP, CutSettings(half_length=10.0))
        self.assertIn("ab NP links 10.0 m, rechts 10.0 m", log)
        doc = ezdxf.readfile(self.dir / f"{sec.file_stem}_NP.dxf")
        layers = {e.dxf.layer for e in doc.modelspace()}
        self.assertTrue({"SCHIENE", "NULLPUNKT", "MAST", "GELAENDE_AUFNAHME"} <= layers)
        for e in doc.modelspace().query("TEXT"):
            self.assertTrue(e.dxf.text.isascii() and "-" not in e.dxf.text, e.dxf.text)
        self.assertIn("2 DP26 DP2a/2.0", [e.dxf.text for e in doc.modelspace().query("TEXT")])

    def test_kote_warning(self):
        sec = self.section(1.06)
        sec.mast_info[0].kote += 5
        log = write_section(sec, self.terrain, self.dir, REF_NP, CutSettings(half_length=10.0))
        self.assertIn("WARNUNG", log)
        self.assertTrue(sec.terrain_warnings)

    def test_project_roundtrip(self):
        path = self.dir / "test.gsproj"
        Project(path, [self.dir / "gelaende.xml"], self.dir / "liste.xlsm", None, self.sections, REF_NP,
                half_length=25.0, zero_height=ZH_RAILS).save()
        loaded = Project.load(path)
        self.assertEqual(len(loaded.sections), len(self.sections))
        self.assertEqual(loaded.half_length, 25.0)
        self.assertEqual(loaded.zero_height, ZH_RAILS)
        self.assertEqual(loaded.sections[0].mast_info, self.sections[0].mast_info)
        self.assertEqual({s.qp for s in loaded.sections if s.warnings}, {"9"})

    def test_load_terrain_order(self):
        (self.dir / "x.xyz").write_text("X Y Z\n" + "\n".join(
            f"{E0 + e} {N0 + n} 400" for e in (0, 1) for n in (0, 1)), encoding="ascii")
        terrain = load_terrain([self.dir / "x.xyz", self.dir / "gelaende.xml"])
        self.assertIsInstance(terrain[0], Mesh)


if __name__ == "__main__":
    unittest.main()
