"""Prüfungen der QP aus der Fundamentliste und Ausrichtung der Blickrichtung.

Die Fehler werden nur gemeldet (sec.warnings und Protokoll), korrigiert wird in der Schnitttabelle.
"""

import re
from collections import Counter

import numpy as np

from .config import CHAIN_WINDOW, CHECK_A, CHECK_JUMP, CHECK_KOTE, SECTION_GAP_KM
from .cutting import terrain_height


def km_groups(items, key):
    """Nach km sortierte Elemente in Abschnitte teilen: neue Gruppe bei einer Lücke grösser SECTION_GAP_KM."""
    groups = []
    for item in items:
        if groups and key(item) - key(groups[-1][-1]) <= SECTION_GAP_KM:
            groups[-1].append(item)
        else:
            groups.append([item])
    return groups


def is_foundation(sec):
    return any(sec.mast_info)


def natural(text):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text)]


def check_sections(sections):
    """Prüft die QP aus der Fundamentliste und richtet sie aus. Setzt sec.warnings, liefert die Meldungen.

    - Abstand Mast zu Fusspunkt weicht mehr als CHECK_A von a ab
    - Lage: je Abschnitt die längste Kette, in der die Abstände der Fusspunkte bis CHECK_JUMP zur Differenz
      der km passen; jedes QP ausserhalb dieser Kette wird gemeldet. So fallen auch mehrere falsche QP in
      Folge auf, die untereinander stimmig sind
    - Mastnummern mehrfach: nur Hinweis
    Blickrichtung: in Richtung steigender km, Punkt 1 links. Der Punkt ohne Namen folgt dem NP.
    """
    secs = [s for s in sections if is_foundation(s) and s.zero_point is not None and s.km is not None]
    for sec in secs:
        sec.warnings = []
        for k, name in enumerate(sec.masts):
            if not name:  # Fusspunkt
                (sec.start if k == 0 else sec.end)[:] = sec.zero_point[:2]
        for _, name, _, point, info in sec.mast_points():
            if info and info.a is not None:
                d = float(np.linalg.norm(point - sec.zero_point[:2]))
                if abs(d - info.a) > CHECK_A:
                    sec.warnings.append(f"Mast {name}: Abstand zum Fusspunkt {d:.2f} m statt a = {info.a:.2f} m")

    for group in km_groups(sorted(secs, key=lambda s: s.km), key=lambda s: s.km):
        chain = consistent_chain(group)
        for i, sec in enumerate(group):
            if i in chain:
                continue
            ref = min(chain, key=lambda k: abs(group[k].km - sec.km))
            d, dk = deviation(group[ref], sec)
            sec.warnings.append(f"Lage passt nicht zur Kilometrierung: Fusspunkt {d:.1f} m vom QP km "
                                f"{group[ref].km:.3f} entfernt, km-Differenz {dk:.1f} m")
        orient(group, chain)

    messages = []
    numbers = Counter(info.number for s in secs for info in s.mast_info if info)
    duplicates = sorted((n for n, c in numbers.items() if c > 1), key=natural)
    if duplicates:
        messages.append(f"HINWEIS Mastnummern mehrfach (Schlüssel ist km mit Nummer): {', '.join(duplicates)}")
    messages += [f"WARNUNG {s.title}: {w}" for s in secs for w in s.warnings]
    return messages


def deviation(a, b):
    """(Abstand der Fusspunkte, km-Differenz) zweier QP in m."""
    return float(np.linalg.norm(a.zero_point[:2] - b.zero_point[:2])), abs(b.km - a.km) * 1000


def consistent_chain(group):
    """Indizes der längsten Kette von QP (nach km), in der aufeinanderfolgende Fusspunkte bis CHECK_JUMP
    zur Differenz der km passen. Einzelne QP dürfen übersprungen werden, höchstens CHAIN_WINDOW in Folge."""
    best, parent = [1] * len(group), [None] * len(group)
    for i in range(len(group)):
        for j in range(max(0, i - CHAIN_WINDOW), i):
            d, dk = deviation(group[j], group[i])
            if abs(d - dk) <= CHECK_JUMP and best[j] + 1 > best[i]:
                best[i], parent[i] = best[j] + 1, j
    i = max(range(len(group)), key=lambda k: best[k])
    chain = set()
    while i is not None:
        chain.add(i)
        i = parent[i]
    return chain


def orient(group, chain):
    """Punkt 1 links, Punkt 2 rechts in Richtung steigender km. Gleisrichtung aus den Fusspunkten der
    nächsten Nachbarn in der stimmigen Kette (anderer km)."""
    valid = sorted(chain)
    for i, sec in enumerate(group):
        prev = next((group[k] for k in reversed(valid) if k < i and group[k].km < sec.km), None)
        nxt = next((group[k] for k in valid if k > i and group[k].km > sec.km), None)
        a = prev.zero_point[:2] if prev else sec.zero_point[:2]
        b = nxt.zero_point[:2] if nxt else sec.zero_point[:2]
        track = b - a
        if not track.any() or sec.length == 0:
            continue
        right = np.array([track[1], -track[0]])
        if (sec.end - sec.start) @ right < 0:
            sec.start, sec.end = sec.end, sec.start
            sec.masts = sec.masts[::-1]
            sec.mast_info = sec.mast_info[::-1]


def terrain_warnings(sec, lines):
    """Kote am Mast gegen das Gelände (Flächen vor Raster). Liefert Meldungen ohne Präfix."""
    result = []
    for station, name, _, _, info in sec.mast_points():
        if info is None or info.kote is None:
            continue
        found = terrain_height(lines, station)
        if found and abs(info.kote - found[1]) > CHECK_KOTE:
            result.append(f"Mast {name}: Kote {info.kote:.2f} liegt {info.kote - found[1]:+.2f} m neben dem "
                          f"Gelände ({found[0]} {found[1]:.2f})")
    return result
