"""Gelände mit der senkrechten Ebene eines QP schneiden."""

from collections import defaultdict

import numpy as np


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


def section_lines(sec, meshes):
    """Geländelinien eines QP als Liste von (Status, Punkte LV95, Stationen ab sec.origin)."""
    if sec.length == 0:
        return []
    lines = []
    for mesh in meshes:
        for pts in cut(mesh, sec.origin, sec.direction):
            stations = (pts[:, :2] - sec.origin) @ sec.direction
            if stations[0] > stations[-1]:  # Linien von links (1. Mast) nach rechts
                pts, stations = pts[::-1], stations[::-1]
            lines.append((mesh.status, pts, stations))
    return lines


def to_profile(lines, shift=(0.0, 0.0)):
    """Geländelinien als 2D-Profil (Status, Stationen, Höhen), um shift = (Station, Höhe) verschoben."""
    s_shift, z_shift = shift
    return [(status, stations - s_shift, pts[:, 2] - z_shift) for status, pts, stations in lines]
