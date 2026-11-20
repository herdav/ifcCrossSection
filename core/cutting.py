"""Gelände mit der senkrechten Ebene eines QP schneiden."""

from collections import defaultdict

import numpy as np

from .config import GRID_BUFFER, GRID_UNLIMITED_HALF_LENGTH, RAIL_LAYER, RAIL_SEARCH, REF_NP, ZH_NONE, ZH_RAILS
from .grid_reader import grid_mesh, section_bbox
from .model import Breakline, CutSettings, Grid, Mesh


def cut(mesh, origin, direction):
    """Schneidet das Mesh mit der senkrechten Ebene durch origin in Richtung direction.

    Liefert eine Liste von Linienzügen (Arrays mit 3D-Punkten in LV95).
    """
    normal = np.array([-direction[1], direction[0]])
    dist = (mesh.verts[:, :2] - origin) @ normal
    below = dist < 0
    faces = mesh.faces[below[mesh.faces].any(1) & ~below[mesh.faces].all(1)]
    if not len(faces):
        return []

    # Jedes geschnittene Dreieck hat genau zwei Kanten, welche die Ebene kreuzen.
    # Die Kante (Indexpaar) identifiziert den Schnittpunkt eindeutig über Nachbardreiecke hinweg.
    edges = np.stack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]], axis=1)
    edges.sort(axis=2)
    crossing = below[edges[..., 0]] != below[edges[..., 1]]
    edges, node_of = np.unique(edges[crossing].reshape(-1, 2), axis=0, return_inverse=True)
    segments = node_of.reshape(-1, 2)

    i, j = edges.T
    t = dist[i] / (dist[i] - dist[j])
    points = mesh.verts[i] + t[:, None] * (mesh.verts[j] - mesh.verts[i])
    return [points[line] for line in chain(segments)]


def chain(segments):
    """Verkettet Segmente (Knotenpaare) zu möglichst langen Linienzügen."""
    neighbours = defaultdict(list)
    for a, b in segments:
        neighbours[a].append(b)
        neighbours[b].append(a)

    lines = []
    # Zuerst an offenen Enden beginnen, danach verbleibende Ringe
    starts = [n for n, nb in neighbours.items() if len(nb) % 2] + list(neighbours)
    for start in starts:
        while neighbours[start]:
            line, node = [start], start
            while neighbours[node]:
                nxt = neighbours[node].pop()
                neighbours[nxt].remove(node)
                line.append(nxt)
                node = nxt
            lines.append(line)
    return lines


def station_range(sec, settings, unlimited=None):
    """(von, bis) der Schnittlänge in Stationen ab sec.origin; None = unbegrenzt."""
    half = settings.half_length if settings.half_length else unlimited
    if half is None:
        return None
    return sec.centre_station - half, sec.centre_station + half


def clip_line(pts, stations, lo, hi):
    """Teile eines Linienzugs zwischen den Stationen lo und hi, an den Grenzen interpoliert."""
    parts, current = [], []
    for k in range(len(pts)):
        if k:
            s_a, s_b = stations[k - 1], stations[k]
            inside = lo <= s_a <= hi
            crossings = sorted((b for b in (lo, hi) if min(s_a, s_b) < b < max(s_a, s_b)), key=lambda b: abs(b - s_a))
            for bound in crossings:
                point = pts[k - 1] + (bound - s_a) / (s_b - s_a) * (pts[k] - pts[k - 1])
                if inside:  # tritt aus: Teil abschliessen
                    parts.append(current + [point])
                    current = []
                else:  # tritt ein
                    current = [point]
                inside = not inside
        if lo <= stations[k] <= hi:
            current.append(pts[k])
    parts.append(current)
    return [np.array(p) for p in parts if len(p) > 1]


def section_lines(sec, terrain, settings=None):
    """Geländelinien eines QP als Liste von (Status, Punkte LV95, Stationen ab sec.origin).

    Flächen und Raster werden geschnitten, Bruchkanten nicht (siehe section_marks).
    """
    settings = settings or CutSettings()
    if sec.length == 0:
        return []
    lines = []
    for item in terrain:
        if isinstance(item, Mesh):
            limits = station_range(sec, settings)
            mesh = item
        elif isinstance(item, Grid):
            limits = station_range(sec, settings, GRID_UNLIMITED_HALF_LENGTH)
            mesh = grid_mesh(item, section_bbox(sec.origin, sec.direction, *limits, GRID_BUFFER))
            if mesh is None:
                continue
        else:
            continue
        for pts in cut(mesh, sec.origin, sec.direction):
            for part in clip_line(pts, (pts[:, :2] - sec.origin) @ sec.direction, *limits) if limits else [pts]:
                stations = (part[:, :2] - sec.origin) @ sec.direction
                if stations[0] > stations[-1]:  # Linien von links (Punkt 1) nach rechts
                    part, stations = part[::-1], stations[::-1]
                lines.append((item.status, part, stations))
    return lines


def section_marks(sec, terrain, settings=None):
    """Durchstosspunkte der Bruchkanten als Liste von (Code, Punkt LV95, Station ab sec.origin)."""
    settings = settings or CutSettings()
    if sec.length == 0:
        return []
    normal = np.array([-sec.direction[1], sec.direction[0]])
    limits = station_range(sec, settings)
    marks = []
    for item in terrain:
        if not isinstance(item, Breakline):
            continue
        dist = (item.points[:, :2] - sec.origin) @ normal
        for k in np.nonzero((dist[:-1] < 0) != (dist[1:] < 0))[0]:
            t = dist[k] / (dist[k] - dist[k + 1])
            point = item.points[k] + t * (item.points[k + 1] - item.points[k])
            station = float((point[:2] - sec.origin) @ sec.direction)
            if limits is None or limits[0] <= station <= limits[1]:
                marks.append((item.code, point, station))
    return sorted(marks, key=lambda m: m[2])


def rail_height(sec, marks):
    """Bestehende SOK am NP: Mittel der Schienen bis RAIL_SEARCH neben dem NP, sonst None."""
    if sec.zero_point is None:
        return None
    heights = [p[2] for code, p, s in marks if code == RAIL_LAYER and abs(s - sec.zero_station) <= RAIL_SEARCH]
    return float(np.mean(heights)) if heights else None


def reference_shift(sec, reference, settings, marks=()):
    """(Station, Höhe) des Bezugspunkts.

    Im Bezug NP der NP, Höhe je nach settings.zero_height: Kote der Tabelle, bestehende SOK aus den
    Schienen (None, wenn keine im Schnitt liegen) oder 0. Sonst bzw. ohne NP 0,0.
    """
    if reference != REF_NP or sec.zero_point is None:
        return 0.0, 0.0
    if settings.zero_height == ZH_NONE:
        return sec.zero_station, 0.0
    if settings.zero_height == ZH_RAILS:
        return sec.zero_station, rail_height(sec, marks)
    return sec.zero_station, sec.zero_point[2]


def terrain_height(lines, station):
    """(Status, Höhe) der ersten Geländelinie, welche die Station überdeckt (Flächen vor Raster), sonst None."""
    for status, pts, stations in lines:
        if stations[0] <= station <= stations[-1]:
            return status, float(np.interp(station, stations, pts[:, 2]))
    return None


def extents(lines):
    """{Status: (kleinste, grösste Station)} der Geländelinien."""
    result = {}
    for status, _, stations in lines:
        lo, hi = result.get(status, (np.inf, -np.inf))
        result[status] = (min(lo, stations.min()), max(hi, stations.max()))
    return result


def to_profile(lines, shift=(0.0, 0.0)):
    """Geländelinien als 2D-Profil (Status, Stationen, Höhen), um shift = (Station, Höhe) verschoben."""
    s_shift, z_shift = shift
    return [(status, stations - s_shift, pts[:, 2] - z_shift) for status, pts, stations in lines]
