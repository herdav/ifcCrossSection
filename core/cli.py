"""Export ohne App: alle IFC und die Excel-Tabelle aus einem Ordner lesen, alle QP als DXF schreiben.

Aufruf:  python main.py export [--data DIR] [--out DIR] [--np]
"""

import argparse
from pathlib import Path

from .config import DATA_DIR, OUTPUT_DIR, REF_LV95, REF_NP
from .dxf_writer import export_sections
from .excel_reader import read_sections
from .ifc_reader import load_meshes
from .model import DataError


def run(data_dir, out_dir, reference):
    ifc_files = sorted(data_dir.glob("*.ifc"))
    xlsx_files = [p for p in sorted(data_dir.glob("*.xlsx")) if not p.name.startswith("~$")]
    if not ifc_files:
        raise DataError(f"Kein IFC in {data_dir}")
    if len(xlsx_files) != 1:
        raise DataError(f"Genau eine Excel-Datei in {data_dir} erwartet, gefunden: {[p.name for p in xlsx_files]}")

    meshes = []
    for path in ifc_files:
        print(f"Lese {path.name} ...")
        meshes += load_meshes(path)
    print(f"  {len(meshes)} Geländeflächen, {sum(len(m.faces) for m in meshes):,} Dreiecke")

    print(f"Lese {xlsx_files[0].name} ...")
    sections, messages = read_sections(xlsx_files[0])
    for line in messages:
        print("  " + line)
    print(f"  {len(sections)} Querprofile")

    print(f"Schreibe nach {out_dir} (Bezug {reference}) ...")
    for line in export_sections(sections, meshes, out_dir, reference):
        print("  " + line)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="main.py export", description="Geländeschnitte aus IFC als DXF exportieren")
    parser.add_argument("--data", type=Path, default=DATA_DIR, help="Ordner mit IFC und Excel")
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR, help="Zielordner für DXF")
    parser.add_argument("--np", action="store_true", help="2D-Profile auf Nullpunkt (NP = 0,0) statt LV95")
    args = parser.parse_args(argv)
    try:
        run(args.data, args.out, REF_NP if args.np else REF_LV95)
    except DataError as exc:
        raise SystemExit(f"FEHLER {exc}")
