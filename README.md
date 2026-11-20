# ifcCrossSection

Querprofile (Geländeschnitte) aus einem Geländemodell schneiden und als DXF exportieren.
Dazu gehört eine PySide6-App zum Prüfen, Bearbeiten und Exportieren der Schnitte.

## Funktionen

- Gelände aus mehreren Quellen, LV95 / LN02:
  - IFC: Geländeflächen (`IfcCivilElement`, `IfcGeographicElement`). Die Georeferenz kommt aus `IfcMapConversion`
    oder aus dem SBB-Objekt «Projektnullpunkt».
  - LandXML: TIN-Surfaces (Punkte «Nord Ost Höhe»).
  - XYZ-Raster, z. B. swissALTI3D (auch als ZIP). Mehrere Kacheln werden zusammengesetzt und nur entlang der
    Schnittlinien trianguliert.
  - DXF: Bruchkanten als 3D-Polylinien je Layer (Schienen, Mauerkrone, Böschung, ...). Im Schnitt erscheinen sie als Marken.
- Schnitttabelle aus Excel, entweder:
  - eigene Tabelle: eine Zeile pro Querprofil (QP), zwei Punkte (z. B. Masten), optional ein Nullpunkt (NP), oder
  - SBB-Vorlage «Fundamentliste» (Blatt `LISTE`): ein QP je Mastposten. Ein Mast allein gibt einen Schnitt durch
    Mast und Fusspunkt, zwei Masten am selben km einen Schnitt durch beide. Der NP ist der Fusspunkt auf der Gleisachse.
    Anker und Druckstützen bekommen kein eigenes QP.
- Blickrichtung bei der Fundamentliste: in Richtung steigender km, links negativ, rechts positiv.
- Prüfungen beim Einlesen (WARNUNG im Protokoll, rote Zeile in der App): Abstand Mast zu Fusspunkt gegen a,
  Lage der Fusspunkte gegen die Kilometrierung, Kote gegen das Gelände am Mast, doppelte Mastnummern (Hinweis).
  Fehler werden nicht korrigiert, sondern in der Schnitttabelle der App berichtigt.
- DXF pro QP, ein Layer pro Geländequelle bzw. Projektstatus:
  - Bezug LV95: `QP01_km1.000.dxf` (2D: Station / Höhe m ü. M.) und `QP01_km1.000_3D.dxf` (3D in LV95)
  - Bezug NP: `QP01_km1.000_NP.dxf` (2D mit dem NP auf 0,0). Höhe des NP wählbar: Kote der Tabelle,
    bestehende SOK aus den Schienen oder keine Verschiebung.
- Schnittlänge beidseits des NP begrenzbar.
- App: 3D-Vorschau mit allen Schnittspuren, Querprofil des aktiven QP mit Überhöhung, bearbeitbare Schnitttabelle,
  Projektdatei (`.gsproj`, JSON) und Export.

## Installation

Python 3.11 oder neuer.

```
python -m pip install -r requirements.txt
```

## Aufruf

```
python main.py [projekt.gsproj]      App starten, optional mit Projektdatei
python main.py export [Optionen]     alle QP ohne App exportieren

Optionen für export:
  --data DIR        Ordner mit Gelände (IFC, LandXML, XYZ, DXF) und genau einer Excel-Datei (.xlsx, .xlsm)
  --out DIR         Zielordner für die DXF
  --np              Bezug NP statt LV95
  --length M        Schnitt beidseits des NP auf M Meter begrenzen
  --np-height H     Höhe des NP: Tabelle (Standard), Schienen oder keine
  --project DATEI   Schnitte zusätzlich als .gsproj speichern
```

Ohne Angabe liest `export` aus `data/` und schreibt nach `data/output/`.
Unter Windows startet `start_app.bat` die App.

## Eigene Schnitttabelle

Erste Zeile mit Spaltennamen, eine Zeile pro QP. X = Ost (E), Y = Nord (N) in LV95.

| QP | KM | Mast 1 | X1 | Y1 | Mast 2 | X2 | Y2 | Nullpunkt X | Nullpunkt Y | Nullpunkt Z |
|----|----|--------|----|----|--------|----|----|-------------|-------------|-------------|

Die Nullpunkt-Spalten sind optional. Spalten der Fundamentliste: siehe `core/config.py`.

## Tests

```
python -m unittest discover tests
```

Die Tests arbeiten mit erfundenen Daten.

## Struktur

```
main.py              Einstieg: App oder export
core/                Kern ohne UI
  config.py          Einstellungen (Layer, Spalten, Toleranzen, Pfade)
  model.py           Section (QP), Mesh, Grid, Breakline, MastInfo, CutSettings
  terrain.py         Gelände nach Dateityp laden
  ifc_reader.py      IFC, Georeferenz, Mesh bereinigen
  landxml_reader.py  LandXML
  grid_reader.py     XYZ-Raster
  breakline_reader.py  Bruchkanten aus DXF
  excel_reader.py    eigene Schnitttabelle
  foundation_reader.py  SBB-Fundamentliste
  checks.py          Prüfungen und Blickrichtung
  cutting.py         Schnitt, Schnittlänge, Marken, NP-Höhe
  dxf_writer.py      DXF 2D / 3D / NP
  project.py         Projektdatei .gsproj
  cli.py             Export ohne App
ui/                  PySide6-App
tests/               Tests mit erfundenen Daten
```
