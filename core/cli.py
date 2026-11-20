"""Export ohne App: Gelände und Schnitttabelle aus einem Ordner lesen, alle QP als DXF schreiben.

Aufruf:  python main.py export [--data DIR] [--out DIR] [--np] [--length M] [--np-height ...] [--project DATEI]
"""

import argparse
from pathlib import Path

from .config import DATA_DIR, OUTPUT_DIR, REF_LV95, REF_NP, ZH_NONE, ZH_RAILS, ZH_TABLE
from .dxf_writer import export_sections
from .excel_reader import read_sections
from .model import CutSettings, DataError
from .project import Project
from .terrain import TERRAIN_SUFFIXES, describe, load_terrain


def find_inputs(data_dir):
    terrain_files = sorted(p for p in data_dir.iterdir() if p.suffix.lower() in TERRAIN_SUFFIXES)
    tables = [p for p in sorted(data_dir.iterdir())
              if p.suffix.lower() in (".xlsx", ".xlsm") and not p.name.startswith("~$")]
    if not any(p.suffix.lower() in (".ifc", ".xml", ".xyz", ".zip") for p in terrain_files):
        raise DataError(f"Kein Gelände (IFC, LandXML, XYZ) in {data_dir}")
    if len(tables) != 1:
        raise DataError(f"Genau eine Excel-Datei in {data_dir} erwartet, gefunden: {[p.name for p in tables]}")
    return terrain_files, tables[0]


def run(data_dir, out_dir, reference, settings, project_path=None):
    terrain_files, table = find_inputs(data_dir)
    print("Lese " + ", ".join(p.name for p in terrain_files) + " ...")
    terrain = load_terrain(terrain_files)
    print("  " + describe(terrain))

    print(f"Lese {table.name} ...")
    sections, messages = read_sections(table)
    for line in messages:
        print("  " + line)
    print(f"  {len(sections)} Querprofile")

    print(f"Schreibe nach {out_dir} (Bezug {reference}) ...")
    for line in export_sections(sections, terrain, out_dir, reference, settings):
        print("  " + line)

    if project_path:
        Project(project_path.resolve(), terrain_files, table, out_dir, sections, reference,
                half_length=settings.half_length, zero_height=settings.zero_height).save()
        print(f"Projekt gespeichert: {project_path}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="main.py export", description="Geländeschnitte als DXF exportieren")
    parser.add_argument("--data", type=Path, default=DATA_DIR,
                        help="Ordner mit Gelände (IFC, LandXML, XYZ, DXF-Bruchkanten) und einer Excel-Datei")
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR, help="Zielordner für DXF")
    parser.add_argument("--np", action="store_true", help="2D-Profile auf Nullpunkt (NP = 0,0) statt LV95")
    parser.add_argument("--length", type=float, default=None,
                        help="Schnitt beidseits des NP begrenzen [m], ohne Angabe ganzes Gelände")
    parser.add_argument("--np-height", choices=(ZH_TABLE, ZH_RAILS, ZH_NONE), default=ZH_TABLE,
                        help="Höhe des NP: Kote der Tabelle, bestehende SOK aus den Schienen oder keine")
    parser.add_argument("--project", type=Path, default=None, help="Schnitte zusätzlich als .gsproj speichern")
    args = parser.parse_args(argv)
    try:
        run(args.data, args.out, REF_NP if args.np else REF_LV95, CutSettings(args.length, args.np_height),
            args.project)
    except DataError as exc:
        raise SystemExit(f"FEHLER {exc}")
