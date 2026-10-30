# ifcCrossSection

Querprofile (Geländeschnitte) aus einem IFC-Geländemodell schneiden und als DXF exportieren.
Dazu gehört eine PySide6-App zum Prüfen, Bearbeiten und Exportieren der Schnitte.

## Funktionen

- Liest Geländeflächen (`IfcCivilElement`, `IfcGeographicElement`) aus IFC und rechnet sie nach LV95 / LN02 um.
  Die Georeferenz kommt aus `IfcMapConversion` oder aus dem SBB-Objekt «Projektnullpunkt».
- Liest die Schnittlinien aus einer Excel-Tabelle: eine Zeile pro Querprofil (QP), definiert durch zwei Punkte
  (z. B. Masten) und optional einen Nullpunkt (NP).
- Schneidet das Gelände mit der senkrechten Ebene durch die beiden Punkte, über die ganze Modellbreite.
  Ist ein NP angegeben, wird der Schnitt parallel durch den NP gelegt.
- Schreibt pro QP DXF-Dateien, ein Layer pro Projektstatus (Bestand, Neubau, ...):
  - Bezug LV95: `QP01_km64.601.dxf` (2D: Station / Höhe m ü. M.) und `QP01_km64.601_3D.dxf` (3D in LV95)
  - Bezug NP: `QP01_km64.601_NP.dxf` (2D mit dem Nullpunkt auf 0,0)
- App: 3D-Vorschau mit allen Schnittspuren, Querprofil des aktiven QP mit Überhöhung, bearbeitbare Schnitttabelle,
  Projektdatei (`.gsproj`, JSON) und Export.

## Installation

Python 3.11 oder neuer.

```
python -m pip install -r requirements.txt
```

## Aufruf

```
python main.py [projekt.gsproj]                         App starten, optional mit Projektdatei
python main.py export [--data DIR] [--out DIR] [--np]   alle QP ohne App exportieren
```

Ohne Angabe liest `export` IFC und Excel aus `data/` und schreibt nach `data/output/`.
Unter Windows startet `start_app.bat` die App.

## Excel-Format

Erste Zeile mit Spaltennamen, eine Zeile pro QP. X = Ost (E), Y = Nord (N) in LV95.

| QP | KM | Mast 1 | X1 | Y1 | Mast 2 | X2 | Y2 | Nullpunkt X | Nullpunkt Y | Nullpunkt Z |
|----|----|--------|----|----|--------|----|----|-------------|-------------|-------------|

Die Nullpunkt-Spalten sind optional.

## Struktur

```
main.py           Einstieg: App oder export
core/             Kern ohne UI
  config.py       Einstellungen (Layer, Farben, Textgrösse, Excel-Spalten, Pfade)
  model.py        Section (QP), Mesh, DataError
  ifc_reader.py   IFC lesen, Georeferenz, Mesh bereinigen
  excel_reader.py Schnitttabelle lesen
  cutting.py      Schnitt und Verkettung der Linien
  dxf_writer.py   DXF 2D / 3D / NP
  project.py      Projektdatei .gsproj
  cli.py          Export ohne App
ui/               PySide6-App
  app.py  main_window.py  terrain_view.py  profile_view.py  section_table.py  theme.py  workers.py
```
