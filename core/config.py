"""Einstellungen und Konstanten des Kerns (IFC, Excel, Bezug, DXF)."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # Ordner mit main.py
DATA_DIR = BASE_DIR / "data"  # IFC und Excel
OUTPUT_DIR = DATA_DIR / "output"  # Standard-Exportordner ohne Projektdatei

# ---------------------------------------------------------------------------- IFC

# IFC-Klassen, die als Gelände geschnitten werden (Passpunkte etc. sind Proxies)
TERRAIN_TYPES = ("IfcCivilElement", "IfcGeographicElement")
STATUS_PSET, STATUS_PROP = "SBB-CFF-FFS", "ObjectStatusProject"
# "cgal-simple" trianguliert TINs ca. 10x schneller als "opencascade"
GEOMETRY_LIBRARY = "cgal-simple"

# Lokale Modellkoordinaten -> LV95: wird aus IfcMapConversion oder dem SBB-Objekt
# "Projektnullpunkt" gelesen. Nur setzen, falls beides fehlt: (E, N, H)
OFFSET = None

# -------------------------------------------------------------------------- Excel

EXCEL_COLUMNS = {"qp": "QP", "km": "KM", "mast1": "Mast 1", "e1": "X1", "n1": "Y1",
                 "mast2": "Mast 2", "e2": "X2", "n2": "Y2"}
EXCEL_ZERO_POINT = ("Nullpunkt X", "Nullpunkt Y", "Nullpunkt Z")  # optional

# -------------------------------------------------------------------------- Bezug

REF_LV95, REF_NP = "LV95", "NP"  # Bezug der DXF: Landeskoordinaten oder Nullpunkt des QP
ZERO_POINT_NOTICE = 0.05  # m, ab diesem Abstand NP zur Mastlinie gibt es einen Hinweis

# ---------------------------------------------------------------------------- DXF

STATUS_COLORS = {"Bestand": 7, "Neubau": 1, "Abbruch": 2}  # ACI, übrige: 3
LAYER_MAST = "MAST"
LAYER_TEXT = "BESCHRIFTUNG"
LAYER_ZERO = "NULLPUNKT"
TEXT_HEIGHT = 0.5  # m
MAST_OVERHANG = 1.0  # Mastlinie ragt so weit über/unter das geschnittene Gelände
