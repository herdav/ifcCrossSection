"""Hauptfenster: Werkzeugleiste, 3D-Vorschau, Querprofil, Schnitttabelle, Protokoll."""

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSplitter, QStyle, QTableView,
    QVBoxLayout, QWidget,
)

from core.checks import check_sections, terrain_warnings
from core.config import (
    DATA_DIR, GRID_BUFFER, GRID_UNLIMITED_HALF_LENGTH, REF_LV95, REF_NP, ZH_NONE, ZH_RAILS, ZH_TABLE,
)
from core.cutting import section_lines, section_marks, station_range
from core.dxf_writer import export_sections
from core.excel_reader import read_sections
from core.grid_reader import grid_patches, section_bbox
from core.model import Breakline, CutSettings, Grid, Mesh, Section
from core.project import PROJECT_SUFFIX, Project
from core.terrain import TERRAIN_SUFFIXES, describe

from .profile_view import ProfileView
from .section_table import SectionModel
from .terrain_view import TerrainView
from .workers import TerrainLoader

APP_NAME = "Geländeschnitte"
PROJECT_FILTER = f"Geländeschnitt-Projekt (*{PROJECT_SUFFIX})"
TERRAIN_FILTER = ("Gelände (" + " ".join(f"*{s}" for s in TERRAIN_SUFFIXES) + ");;IFC (*.ifc);;LandXML (*.xml);;"
                  "Raster XYZ (*.xyz *.zip);;Bruchkanten DXF (*.dxf)")
GRID_VIEW_MARGIN = 10.0  # m, Raster in der 3D-Ansicht so weit um die Schnittlinien


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1600, 950)
        self.project = Project()  # Pfade und Exportordner; Schnitte, Bezug usw. leben in den Widgets
        self.terrain = []  # Mesh, Grid, Breakline
        self.cut_cache = {}
        self.loader = None
        self.dirty = False

        self.model = SectionModel()
        self.model.section_edited.connect(self.on_section_edited)
        self.terrain_view = TerrainView()
        self.profile_view = ProfileView()
        self.profile_view.hovered.connect(self.statusBar().showMessage)

        self.build_toolbar()
        self.build_layout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(160)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.show_section()
        self.update_title()

    # ---------------------------------------------------------------- Aufbau

    def build_toolbar(self):
        tb = self.addToolBar("Hauptleiste")
        tb.setMovable(False)

        def action(text, slot, shortcut=None):
            act = QAction(text, self)
            act.triggered.connect(slot)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
                act.setToolTip(f"{text} ({QKeySequence(shortcut).toString()})")
            tb.addAction(act)

        action("Gelände laden…", self.load_terrain_dialog, "Ctrl+I")
        action("Excel laden…", self.load_excel_dialog, "Ctrl+L")
        tb.addSeparator()
        action("Projekt öffnen…", self.open_project_dialog, QKeySequence.Open)
        action("Projekt speichern", self.save_project, QKeySequence.Save)
        action("Speichern unter…", self.save_project_as, QKeySequence.SaveAs)
        tb.addSeparator()
        tb.addWidget(QLabel(" Bezug "))
        self.reference_box = QComboBox()
        self.reference_box.addItem("LV95 (2D + 3D)", REF_LV95)
        self.reference_box.addItem("NP = 0,0 (nur 2D)", REF_NP)
        self.reference_box.setToolTip("Bezug für Export und Querprofil")
        self.reference_box.currentIndexChanged.connect(self.on_settings)
        tb.addWidget(self.reference_box)
        tb.addWidget(QLabel(" NP-Höhe "))
        self.zero_height_box = QComboBox()
        self.zero_height_box.addItem("Kote Tabelle", ZH_TABLE)
        self.zero_height_box.addItem("bestehende SOK", ZH_RAILS)
        self.zero_height_box.addItem("keine (m ü. M.)", ZH_NONE)
        self.zero_height_box.setToolTip("Höhe des NP im Bezug NP: Kote aus der Tabelle (Fundamentliste: neue SOK), "
                                        "Mittel der gemessenen Schienen am NP oder keine Verschiebung")
        self.zero_height_box.currentIndexChanged.connect(self.on_settings)
        tb.addWidget(self.zero_height_box)
        tb.addWidget(QLabel(" Schnitt ± "))
        self.half_length = QDoubleSpinBox()
        self.half_length.setRange(0.0, 1000.0)
        self.half_length.setSingleStep(5.0)
        self.half_length.setDecimals(1)
        self.half_length.setSuffix(" m")
        self.half_length.setSpecialValueText("ganz")
        self.half_length.setToolTip("Schnitt beidseits des NP begrenzen (ohne NP: der Mitte). 0 = ganzes Gelände")
        self.half_length.valueChanged.connect(self.on_half_length)
        tb.addWidget(self.half_length)
        action("Exportordner…", self.choose_out_dir)
        action("Export alle QP", self.export_all, "Ctrl+E")
        action("Export aktueller QP", self.export_current, "Ctrl+Shift+E")
        tb.addSeparator()

        tb.addWidget(QLabel(" Überhöhung "))
        self.exaggeration = QDoubleSpinBox()
        self.exaggeration.setRange(1.0, 10.0)
        self.exaggeration.setSingleStep(0.5)
        self.exaggeration.setValue(1.0)
        self.exaggeration.setSuffix(" x")
        self.exaggeration.valueChanged.connect(self.on_exaggeration)
        tb.addWidget(self.exaggeration)
        self.follow = QCheckBox("Kamera folgt QP")
        self.follow.setChecked(True)
        tb.addWidget(self.follow)

    def build_layout(self):
        left = QSplitter(Qt.Vertical)
        left.addWidget(self.terrain_view)
        left.addWidget(self.profile_view)
        left.setSizes([600, 300])

        self.prev_button = QPushButton(self.style().standardIcon(QStyle.SP_ArrowLeft), " Zurück")
        self.next_button = QPushButton(self.style().standardIcon(QStyle.SP_ArrowRight), " Weiter")
        self.next_button.setLayoutDirection(Qt.RightToLeft)  # Pfeil rechts vom Text
        self.prev_button.setShortcut(QKeySequence("PgUp"))
        self.next_button.setShortcut(QKeySequence("PgDown"))
        self.prev_button.setToolTip("Vorheriger QP (Bild auf)")
        self.next_button.setToolTip("Nächster QP (Bild ab)")
        self.prev_button.clicked.connect(lambda: self.step(-1))
        self.next_button.clicked.connect(lambda: self.step(1))
        self.nav_label = QLabel()
        self.nav_label.setAlignment(Qt.AlignCenter)
        font = self.nav_label.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() + 1)
        self.nav_label.setFont(font)
        nav = QHBoxLayout()
        nav.addWidget(self.prev_button)
        nav.addWidget(self.nav_label, 1)
        nav.addWidget(self.next_button)

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.selectionModel().currentRowChanged.connect(lambda *_: self.show_section())

        add_button = QPushButton("QP hinzufügen")
        remove_button = QPushButton("QP löschen")
        add_button.clicked.connect(self.add_section)
        remove_button.clicked.connect(self.remove_section)
        row_buttons = QHBoxLayout()
        row_buttons.addWidget(add_button)
        row_buttons.addWidget(remove_button)
        row_buttons.addStretch()

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.log.setPlaceholderText("Protokoll")

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addLayout(nav)
        right_layout.addWidget(self.table, 3)
        right_layout.addLayout(row_buttons)
        right_layout.addWidget(self.log, 1)

        main = QSplitter(Qt.Horizontal)
        main.addWidget(left)
        main.addWidget(right)
        main.setSizes([900, 700])
        self.setCentralWidget(main)

    # ------------------------------------------------------------- Zustand

    def log_msg(self, text):
        for line in str(text).strip().splitlines():
            self.log.appendPlainText(line.strip())

    def set_dirty(self, dirty=True):
        self.dirty = dirty
        self.update_title()

    def update_title(self):
        name = self.project.path.name if self.project.path else "neues Projekt"
        self.setWindowTitle(f"{APP_NAME} [{name}]{'*' if self.dirty else ''}")

    def current_row(self):
        return self.table.currentIndex().row() if self.model.sections else -1

    def current_section(self):
        row = self.current_row()
        return self.model.sections[row] if 0 <= row < len(self.model.sections) else None

    def select_row(self, row):
        if not self.model.sections:
            self.show_section()
            return
        row = max(0, min(row, len(self.model.sections) - 1))
        index = self.model.index(row, max(self.table.currentIndex().column(), 0))
        self.table.setCurrentIndex(index)
        self.table.scrollTo(index)
        self.show_section()

    def settings(self):
        return CutSettings(self.half_length.value() or None, self.zero_height_box.currentData())

    def cut_for(self, sec):
        """(Geländelinien, Marken) eines QP, zwischengespeichert."""
        settings = self.settings()
        # NP verschiebt die Schnittlinie, die Schnittlänge hängt am NP
        key = (sec.start.tobytes(), sec.end.tobytes(), sec.offset, sec.centre_station, settings.half_length)
        if key not in self.cut_cache:
            self.cut_cache[key] = (section_lines(sec, self.terrain, settings),
                                   section_marks(sec, self.terrain, settings))
        return self.cut_cache[key]

    def lines_for(self, sec):
        return self.cut_for(sec)[0]

    def show_section(self, focus=True):
        sec = self.current_section()
        lines, marks = self.cut_for(sec) if sec else ([], [])
        self.profile_view.set_profile(sec, lines, self.reference(), self.settings(), marks)
        self.terrain_view.set_active(sec, lines, marks)
        if sec and focus and self.follow.isChecked():
            self.terrain_view.focus(sec, lines)
        row, count = self.current_row(), len(self.model.sections)
        self.nav_label.setText(f"{sec.title}   ({row + 1}/{count})" if sec else "Kein QP")
        self.prev_button.setEnabled(row > 0)
        self.next_button.setEnabled(0 <= row < count - 1)

    def refresh_traces(self):
        """Schnittspuren aller QP und Prüfung der Koten gegen das Gelände."""
        all_lines = []
        for sec in self.model.sections:
            lines = self.lines_for(sec)
            sec.terrain_warnings = terrain_warnings(sec, lines)
            all_lines.append(lines)
        self.terrain_view.set_traces(all_lines)
        self.model.refresh()

    def recheck(self):
        """Prüfungen der Tabelle neu (z. B. nach einer Korrektur); liefert die Meldungen."""
        messages = check_sections(self.model.sections)
        self.model.refresh()
        return messages

    def step(self, delta):
        self.select_row(self.current_row() + delta)

    # ------------------------------------------------------------- Schnitte

    def on_section_edited(self, row):
        self.set_dirty()
        self.recheck()
        self.refresh_traces()
        if row == self.current_row():
            self.show_section(focus=False)

    def reference(self):
        return self.reference_box.currentData()

    def on_settings(self):
        self.set_dirty()
        self.show_section(focus=False)

    def on_half_length(self):
        self.set_dirty()
        self.refresh_traces()
        self.show_section(focus=False)

    def on_exaggeration(self, value):
        self.profile_view.set_exaggeration(value)
        self.terrain_view.set_exaggeration(value)
        self.refresh_traces()
        self.show_section()

    def add_section(self):
        base = self.current_section()
        numbers = [int(s.qp) for s in self.model.sections if s.qp.isdigit()]
        sec = Section(
            qp=str(max(numbers, default=0) + 1),
            km=base.km if base else None,
            masts=("", ""),
            start=base.start.copy() if base else np.zeros(2),
            end=base.end.copy() if base else np.array([0.0, 10.0]),
        )
        row = self.current_row() + 1
        self.model.insert(row, sec)
        self.set_dirty()
        self.refresh_traces()
        self.select_row(row)
        self.log_msg(f"{sec.title} hinzugefügt (Koordinaten von {base.title if base else 'Nullpunkt'} kopiert)")

    def remove_section(self):
        sec = self.current_section()
        if sec is None:
            return
        row = self.current_row()
        self.model.remove(row)
        self.set_dirty()
        self.recheck()
        self.refresh_traces()
        self.select_row(row)
        self.log_msg(f"{sec.title} gelöscht")

    # ---------------------------------------------------------------- Laden

    def start_dir(self):
        for path in (self.project.path, self.project.excel_path, *self.project.terrain_paths):
            if path:
                return str(Path(path).parent)
        return str(DATA_DIR)

    def load_terrain_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Gelände laden", self.start_dir(), TERRAIN_FILTER)
        if paths:
            self.project.terrain_paths = [Path(p) for p in paths]
            self.set_dirty()
            self.load_terrain()

    def load_terrain(self):
        if self.loader and self.loader.isRunning():
            self.log_msg("Gelände wird bereits geladen")
            return
        self.log_msg("Lese " + ", ".join(p.name for p in self.project.terrain_paths) + " ...")
        self.progress.show()
        self.loader = TerrainLoader(self.project.terrain_paths)
        self.loader.loaded.connect(self.on_terrain_loaded)
        self.loader.failed.connect(self.on_load_failed)
        self.loader.start()

    def view_meshes(self):
        """Flächen für die 3D-Ansicht; Raster nur in Streifen um die Schnittlinien."""
        meshes = [t for t in self.terrain if isinstance(t, Mesh)]
        for grid in (t for t in self.terrain if isinstance(t, Grid)):
            bboxes = []
            for sec in self.model.sections:
                if sec.length:
                    limits = station_range(sec, self.settings(), GRID_UNLIMITED_HALF_LENGTH)
                    bboxes.append(section_bbox(sec.origin, sec.direction, *limits, GRID_VIEW_MARGIN + GRID_BUFFER))
            patch = grid_patches(grid, bboxes)
            if patch is not None:
                meshes.append(patch)
        return meshes

    def on_terrain_loaded(self, terrain):
        self.progress.hide()
        self.terrain = terrain
        self.cut_cache.clear()
        self.terrain_view.set_exaggeration(self.exaggeration.value())
        self.terrain_view.set_meshes(self.view_meshes())
        self.terrain_view.set_breaklines([t for t in terrain if isinstance(t, Breakline)])
        self.log_msg(describe(terrain))
        self.refresh_traces()
        for sec in self.model.sections:
            for w in sec.terrain_warnings:
                self.log_msg(f"WARNUNG {sec.title}: {w}")
        self.show_section()

    def on_load_failed(self, message):
        self.progress.hide()
        self.log_msg(f"FEHLER beim Laden: {message}")
        QMessageBox.critical(self, "Gelände laden", message)

    def load_excel_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Excel laden (Schnitttabelle oder Fundamentliste)",
                                              self.start_dir(), "Excel (*.xlsx *.xlsm)")
        if not path:
            return
        if self.model.sections and QMessageBox.question(
                self, "Excel laden", "Die aktuelle Schnitttabelle wird ersetzt. Fortfahren?") != QMessageBox.Yes:
            return
        try:
            sections, messages = read_sections(Path(path))
        except Exception as exc:
            QMessageBox.critical(self, "Excel laden", str(exc))
            return
        for line in messages:
            self.log_msg(line)
        self.project.excel_path = Path(path)
        self.model.reset(sections)
        self.log_msg(f"{len(sections)} QP aus {self.project.excel_path.name} gelesen")
        self.set_dirty()
        if any(isinstance(t, Grid) for t in self.terrain):
            self.terrain_view.set_meshes(self.view_meshes())
        self.refresh_traces()
        self.select_row(0)

    # --------------------------------------------------------------- Projekt

    def maybe_save(self):
        """Fragt bei ungespeicherten Änderungen nach. False = Abbrechen."""
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, APP_NAME, "Änderungen am Projekt speichern?",
                                      QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if answer == QMessageBox.Save:
            return self.save_project()
        return answer == QMessageBox.Discard

    def open_project_dialog(self):
        if not self.maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Projekt öffnen", self.start_dir(), PROJECT_FILTER)
        if path:
            self.open_project(Path(path))

    def open_project(self, path):
        try:
            project = Project.load(path)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            QMessageBox.critical(self, "Projekt öffnen", f"{Path(path).name} kann nicht gelesen werden:\n{exc}")
            return

        self.project = project
        self.model.reset(project.sections)
        self.terrain = []
        self.cut_cache.clear()
        self.terrain_view.set_meshes([])
        self.terrain_view.set_breaklines([])
        self.exaggeration.setValue(project.exaggeration)
        self.half_length.setValue(project.half_length or 0.0)
        self.reference_box.setCurrentIndex(max(self.reference_box.findData(project.reference), 0))
        self.zero_height_box.setCurrentIndex(max(self.zero_height_box.findData(project.zero_height), 0))
        self.select_row(project.current)
        self.log_msg(f"Projekt {project.path.name} geöffnet, {len(project.sections)} QP")
        for line in project.messages:
            self.log_msg(line)

        missing = [p for p in project.terrain_paths if not p.exists()]
        for p in missing:
            self.log_msg(f"WARNUNG Geländedatei nicht gefunden: {p}")
        project.terrain_paths = [p for p in project.terrain_paths if p.exists()]
        if project.terrain_paths:
            self.load_terrain()
        self.set_dirty(bool(missing))

    def save_project(self):
        if not self.project.path:
            return self.save_project_as()
        self.project.sections = self.model.sections
        self.project.reference = self.reference()
        self.project.exaggeration = self.exaggeration.value()
        self.project.half_length = self.settings().half_length
        self.project.zero_height = self.settings().zero_height
        self.project.current = self.current_row()
        try:
            self.project.save()
        except OSError as exc:
            QMessageBox.critical(self, "Projekt speichern", str(exc))
            return False
        self.log_msg(f"Projekt gespeichert: {self.project.path.name}")
        self.set_dirty(False)
        return True

    def save_project_as(self):
        default = self.project.path or Path(self.start_dir()) / f"Gelaendeschnitte{PROJECT_SUFFIX}"
        path, _ = QFileDialog.getSaveFileName(self, "Projekt speichern", str(default), PROJECT_FILTER)
        if not path:
            return False
        self.project.path = Path(path).with_suffix(PROJECT_SUFFIX)
        return self.save_project()

    # ---------------------------------------------------------------- Export

    def choose_out_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Exportordner", str(self.project.export_dir))
        if path:
            self.project.out_dir = Path(path)
            self.set_dirty()
            self.log_msg(f"Exportordner: {self.project.out_dir}")

    def export_all(self):
        self.export(self.model.sections)

    def export_current(self):
        sec = self.current_section()
        self.export([sec] if sec else [])

    def export(self, sections):
        if not any(isinstance(t, (Mesh, Grid)) for t in self.terrain):
            QMessageBox.information(self, "Export", "Zuerst ein Gelände laden.")
            return
        if not sections:
            return
        out_dir = self.project.export_dir
        reference = self.reference()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            results = export_sections(sections, self.terrain, out_dir, reference, self.settings())
        except OSError as exc:
            results = [f"FEHLER {exc}"]
        finally:
            QApplication.restoreOverrideCursor()
        for line in results:
            self.log_msg(line)
        errors = sum("FEHLER" in line for line in results)
        self.model.refresh()
        self.log_msg(f"Export Bezug {reference} nach {out_dir}: {len(sections) - errors} QP ok, {errors} Fehler")
        self.statusBar().showMessage(f"{len(sections) - errors} QP exportiert", 5000)

    # ---------------------------------------------------------------- Ende

    def closeEvent(self, event):
        if not self.maybe_save():
            event.ignore()
            return
        if self.loader and self.loader.isRunning():
            self.loader.wait()
        self.terrain_view.plotter.close()
        event.accept()
