"""Einstellungen und Konstanten des Kerns (Gelände, Tabellen, Bezug, Prüfungen, DXF)."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # Ordner mit main.py
DATA_DIR = BASE_DIR / "data"  # Gelände und Schnitttabelle
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

# ------------------------------------------------------------- weitere Geländedaten

LANDXML_STATUS = "Aufnahme"  # Status (Layer) der Flächen aus LandXML
LANDXML_WELD_DECIMALS = 3  # Punkte auf 1 mm verschweissen (Aufnahmen haben Punkte im Zehntelmillimeter-Abstand)
GRID_STATUS = "swissALTI3D"  # Status der Raster (XYZ, z. B. swissALTI3D)
GRID_BUFFER = 1.0  # m, Rasterzellen so weit neben der Schnittlinie werden trianguliert
GRID_UNLIMITED_HALF_LENGTH = 50.0  # m, Schnittlänge im Raster, wenn sie nicht begrenzt ist

# Bruchkanten aus DXF (3D-Polylinien je Layer). Die Schienen geben die bestehende SOK und Gleismitte.
RAIL_LAYER = "Gleis-Querprofil"
BREAKLINE_LAYERS = (RAIL_LAYER, "Mauerkrone", "Mauerfuss", "Boeschung_OK", "Boeschung_UK", "Fundament",
                    "Kabelschacht_eck", "Kabelschacht_zus")
RAIL_SEARCH = 1.5  # m, Schienen so weit beidseits des NP zählen für die bestehende SOK

# -------------------------------------------------------------------------- Excel

# Eigene Schnitttabelle: eine Zeile pro QP mit zwei Punkten
EXCEL_COLUMNS = {"qp": "QP", "km": "KM", "mast1": "Mast 1", "e1": "X1", "n1": "Y1",
                 "mast2": "Mast 2", "e2": "X2", "n2": "Y2"}
EXCEL_ZERO_POINT = ("Nullpunkt X", "Nullpunkt Y", "Nullpunkt Z")  # optional

# SBB-Vorlage «Fundamentliste»: Blatt und erste Datenzeile, Spalten als Buchstaben
FOUNDATION_SHEET = "LISTE"
FOUNDATION_FIRST_ROW = 18
FOUNDATION_COLUMNS = {"km": "A", "number": "B", "mast_type": "C", "track": "D", "a": "F",
                      "foot_e": "H", "foot_n": "I", "mast_e": "L", "mast_n": "M", "kote": "N",
                      "foundation": "Y"}
SECTION_GAP_KM = 0.2  # km, grössere Lücken in der Kilometrierung trennen die Abschnitte
PAIR_DISTANCE = 0.5  # m, zwei Masten am selben km mit so nahen Fusspunkten bilden ein QP

# -------------------------------------------------------------------------- Bezug

REF_LV95, REF_NP = "LV95", "NP"  # Bezug der DXF: Landeskoordinaten oder Nullpunkt des QP
ZERO_POINT_NOTICE = 0.05  # m, ab diesem Abstand NP zur Mastlinie gibt es einen Hinweis

# Höhe des NP im Bezug NP: Kote aus der Tabelle, bestehende SOK aus den Schienen oder keine Verschiebung
ZH_TABLE, ZH_RAILS, ZH_NONE = "Tabelle", "Schienen", "keine"

# ----------------------------------------------------------------------- Prüfungen

CHECK_A = 0.05  # m, Abstand Mast zu Fusspunkt darf so weit von a abweichen
CHECK_JUMP = 5.0  # m, Abstand der Fusspunkte zweier Nachbarn gegen die Differenz der km
CHAIN_WINDOW = 8  # so viele QP in Folge darf die Lageprüfung als falsch überspringen
CHECK_KOTE = 1.0  # m, Kote am Mast gegen das Gelände

# ---------------------------------------------------------------------------- DXF

STATUS_COLORS = {"Bestand": 7, "Neubau": 1, "Abbruch": 2, LANDXML_STATUS: 7, GRID_STATUS: 8}  # ACI, übrige: 3
LAYER_MAST = "MAST"
LAYER_TEXT = "BESCHRIFTUNG"
LAYER_ZERO = "NULLPUNKT"
LAYER_RAIL = "SCHIENE"
LAYER_BREAKLINE = "BRUCHKANTE"
TEXT_HEIGHT = 0.5  # m
MAST_OVERHANG = 1.0  # Mastlinie ragt so weit über/unter das geschnittene Gelände
MARK_SIZE = 0.15  # m, Marken für Schienen und Bruchkanten
