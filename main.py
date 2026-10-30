"""
Geländeschnitte RONS: Querprofile aus dem IFC-Geländemodell schneiden und als DXF exportieren.

Aufruf:
  python main.py [projekt.gsproj]                       App starten, optional mit Projektdatei
  python main.py export [--data DIR] [--out DIR] [--np]  DXF ohne App exportieren (alle QP)

Benötigt: ifcopenshell, numpy, openpyxl, ezdxf; für die App zusätzlich PySide6, pyvista, pyvistaqt
"""

import sys


def main():
    args = sys.argv[1:]
    if args[:1] == ["export"]:
        from core.cli import main as export_main
        export_main(args[1:])
    elif args[:1] in (["-h"], ["--help"]):
        print(__doc__.strip())
    else:
        from ui.app import run
        run(args[0] if args else None)


if __name__ == "__main__":
    main()
