"""Bearbeitbare Schnitttabelle: eine Zeile pro QP mit beiden Punkten und optionalem NP."""

import numpy as np
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal

COLUMNS = ("QP", "km", "Mast 1", "E 1", "N 1", "Mast 2", "E 2", "N 2", "NP E", "NP N", "NP H")
NUMBER_COLUMNS = (1, 3, 4, 6, 7, 8, 9, 10)
ZERO_COLUMNS = (8, 9, 10)


def parse_number(text):
    return float(text.replace("'", "").replace(",", "."))


class SectionModel(QAbstractTableModel):
    """Eine Zeile pro QP mit beiden Punkten; Änderungen wirken direkt auf die Section-Objekte."""

    section_edited = Signal(int)

    def __init__(self):
        super().__init__()
        self.sections = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.sections)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        return None

    def flags(self, index):
        return super().flags(index) | Qt.ItemIsEditable

    def data(self, index, role=Qt.DisplayRole):
        sec, col = self.sections[index.row()], index.column()
        if role in (Qt.DisplayRole, Qt.EditRole):
            zero = ["", "", ""] if sec.zero_point is None else [f"{v:.3f}" for v in sec.zero_point]
            return [
                sec.qp, "" if sec.km is None else f"{sec.km:.3f}",
                sec.masts[0], f"{sec.start[0]:.3f}", f"{sec.start[1]:.3f}",
                sec.masts[1], f"{sec.end[0]:.3f}", f"{sec.end[1]:.3f}", *zero,
            ][col]
        if role == Qt.ToolTipRole and col in ZERO_COLUMNS:
            return "Nullpunkt des QP (leer = kein NP). Der Schnitt wird parallel durch den NP gelegt."
        if role == Qt.TextAlignmentRole and col in NUMBER_COLUMNS:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole:
            return False
        sec, col, text = self.sections[index.row()], index.column(), str(value).strip()
        try:
            if col == 0:
                if not text:
                    return False
                sec.qp = text
            elif col == 1:
                sec.km = parse_number(text) if text else None
            elif col in (2, 5):
                masts = list(sec.masts)
                masts[0 if col == 2 else 1] = text
                sec.masts = tuple(masts)
            elif col in ZERO_COLUMNS:
                if not text:
                    sec.zero_point = None
                else:
                    if sec.zero_point is None:  # neuer NP startet auf Mast 1
                        sec.zero_point = np.array([*sec.start, 0.0])
                    sec.zero_point[col - ZERO_COLUMNS[0]] = parse_number(text)
            else:
                point = sec.start if col in (3, 4) else sec.end
                point[0 if col in (3, 6) else 1] = parse_number(text)
        except ValueError:
            return False
        self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), len(COLUMNS) - 1))
        self.section_edited.emit(index.row())
        return True

    def reset(self, sections):
        self.beginResetModel()
        self.sections = sections
        self.endResetModel()

    def insert(self, row, sec):
        self.beginInsertRows(QModelIndex(), row, row)
        self.sections.insert(row, sec)
        self.endInsertRows()

    def remove(self, row):
        self.beginRemoveRows(QModelIndex(), row, row)
        del self.sections[row]
        self.endRemoveRows()
