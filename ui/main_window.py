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

from core.config import DATA_DIR, REF_LV95, REF_NP
from core.cutting import section_lines
from core.dxf_writer import export_sections
from core.excel_reader import read_sections
from core.model import Section
from core.project import PROJECT_SUFFIX, Project

from .profile_view import ProfileView
from .section_table import SectionModel
from .terrain_view import TerrainView
from .workers import MeshLoader

APP_NAME = "Geländeschnitte"
PROJECT_FILTER = f"Geländeschnitt-Projekt (*{PROJECT_SUFFIX})"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1600, 950)
        self.project = Project()  # Pfade und Exportordner; Schnitte, Bezug usw. leben in den Widgets
        self.meshes = []
        self.lines_cache = {}
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

        action("IFC laden…", self.load_ifc_dialog, "Ctrl+I")
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
        self.reference_box.currentIndexChanged.connect(self.on_reference)
        tb.addWidget(self.reference_box)
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

    def lines_for(self, sec):
        key = (sec.start.tobytes(), sec.end.tobytes(), sec.offset)  # NP verschiebt die Schnittlinie
        if key not in self.lines_cache:
            self.lines_cache[key] = section_lines(sec, self.meshes)
        return self.lines_cache[key]

    def show_section(self, focus=True):
        sec = self.current_section()
        lines = self.lines_for(sec) if sec else []
        self.profile_view.set_profile(sec, lines, self.reference())
        self.terrain_view.set_active(sec, lines)
        if sec and focus and self.follow.isChecked():
            self.terrain_view.focus(sec, lines)
        row, count = self.current_row(), len(self.model.sections)
        self.nav_label.setText(f"{sec.title}   ({row + 1}/{count})" if sec else "Kein QP")
        self.prev_button.setEnabled(row > 0)
        self.next_button.setEnabled(0 <= row < count - 1)

    def refresh_traces(self):
        self.terrain_view.set_traces([self.lines_for(sec) for sec in self.model.sections])

    def step(self, delta):
        self.select_row(self.current_row() + delta)

    # ------------------------------------------------------------- Schnitte

    def on_section_edited(self, row):
        self.set_dirty()
        self.refresh_traces()
        if row == self.current_row():
            self.show_section(focus=False)

    def reference(self):
        return self.reference_box.currentData()

    def on_reference(self):
        self.set_dirty()
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
        self.refresh_traces()
        self.select_row(row)
        self.log_msg(f"{sec.title} gelöscht")

    # ---------------------------------------------------------------- Laden

    def start_dir(self):
        for path in (self.project.path, self.project.excel_path, *self.project.ifc_paths):
            if path:
                return str(Path(path).parent)
        return str(DATA_DIR)

    def load_ifc_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "IFC laden", self.start_dir(), "IFC (*.ifc)")
        if paths:
            self.project.ifc_paths = [Path(p) for p in paths]
            self.set_dirty()
            self.load_meshes()

    def load_meshes(self):
        if self.loader and self.loader.isRunning():
            self.log_msg("IFC wird bereits geladen")
            return
        self.log_msg("Lese " + ", ".join(p.name for p in self.project.ifc_paths) + " ...")
        self.progress.show()
        self.loader = MeshLoader(self.project.ifc_paths)
        self.loader.loaded.connect(self.on_meshes_loaded)
        self.loader.failed.connect(self.on_load_failed)
        self.loader.start()

    def on_meshes_loaded(self, meshes):
        self.progress.hide()
        self.meshes = meshes
        self.lines_cache.clear()
        self.terrain_view.set_exaggeration(self.exaggeration.value())
        self.terrain_view.set_meshes(meshes)
        triangles = f"{sum(len(m.faces) for m in meshes):,}".replace(",", "'")
        self.log_msg(f"{len(meshes)} Geländeflächen, {triangles} Dreiecke")
        self.refresh_traces()
        self.show_section()

    def on_load_failed(self, message):
        self.progress.hide()
        self.log_msg(f"FEHLER beim Laden: {message}")
        QMessageBox.critical(self, "IFC laden", message)

    def load_excel_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Excel laden", self.start_dir(), "Excel (*.xlsx)")
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
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.critical(self, "Projekt öffnen", f"{Path(path).name} kann nicht gelesen werden:\n{exc}")
            return

        self.project = project
        self.model.reset(project.sections)
        self.meshes = []
        self.lines_cache.clear()
        self.terrain_view.set_meshes([])
        self.exaggeration.setValue(project.exaggeration)
        self.reference_box.setCurrentIndex(max(self.reference_box.findData(project.reference), 0))
        self.select_row(project.current)
        self.log_msg(f"Projekt {project.path.name} geöffnet, {len(project.sections)} QP")

        missing = [p for p in project.ifc_paths if not p.exists()]
        for p in missing:
            self.log_msg(f"WARNUNG IFC nicht gefunden: {p}")
        project.ifc_paths = [p for p in project.ifc_paths if p.exists()]
        if project.ifc_paths:
            self.load_meshes()
        self.set_dirty(bool(missing))

    def save_project(self):
        if not self.project.path:
            return self.save_project_as()
        self.project.sections = self.model.sections
        self.project.reference = self.reference()
        self.project.exaggeration = self.exaggeration.value()
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
        if not self.meshes:
            QMessageBox.information(self, "Export", "Zuerst ein IFC laden.")
            return
        if not sections:
            return
        out_dir = self.project.export_dir
        reference = self.reference()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            results = export_sections(sections, self.meshes, out_dir, reference)
        except OSError as exc:
            results = [f"FEHLER {exc}"]
        finally:
            QApplication.restoreOverrideCursor()
        for line in results:
            self.log_msg(line)
        errors = sum("FEHLER" in line for line in results)
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
