"""Bruchkanten (3D-Polylinien) aus DXF lesen, je Layer ein Code. Die Schienen liegen auf RAIL_LAYER."""

import ezdxf
import numpy as np

from .config import BREAKLINE_LAYERS
from .model import Breakline, DataError


def load_breaklines(path, layers=BREAKLINE_LAYERS):
    try:
        doc = ezdxf.readfile(path)
    except (OSError, ezdxf.DXFError) as exc:
        raise DataError(f"{path.name}: DXF nicht lesbar ({exc})") from None
    wanted = {layer.lower(): layer for layer in layers}
    lines = []
    for e in doc.modelspace().query("POLYLINE LINE"):
        code = wanted.get(e.dxf.layer.lower())
        if code is None:
            continue
        if e.dxftype() == "LINE":
            pts = [e.dxf.start, e.dxf.end]
        elif e.is_3d_polyline:
            pts = list(e.points())
            if e.is_closed:
                pts.append(pts[0])
        else:
            continue
        if len(pts) > 1:
            lines.append(Breakline(code, np.array([tuple(p) for p in pts], float)))
    return lines
