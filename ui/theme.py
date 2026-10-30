"""Dark Mode und Farben der Ansichten."""

from PySide6.QtGui import QColor, QPalette

BG = "#1e1f22"
GRID = "#383a3f"
LINE_COLORS = {"Bestand": "#d4d4d4", "Neubau": "#ff5c5c", "Abbruch": "#ffd54f"}  # wie DXF-Layer
TERRAIN_COLORS = {"Bestand": "#a39a8a", "Neubau": "#c0504d", "Abbruch": "#c9a227"}
OTHER_COLOR = "#81c784"
MAST_COLOR = "#4fc3f7"
TRACE_COLOR = "#6fa8dc"
ACTIVE_COLOR = "#ffca28"
ZERO_COLOR = "#e040fb"  # Nullpunkt, wie DXF-Layer NULLPUNKT (magenta)


def apply_dark_theme(app):
    app.setStyle("Fusion")
    window, base, text, accent = QColor("#2b2d30"), QColor(BG), QColor("#dcdcdc"), QColor("#3d8ee6")
    pal = QPalette()
    for role, color in {
        QPalette.Window: window, QPalette.WindowText: text, QPalette.Base: base, QPalette.AlternateBase: window,
        QPalette.ToolTipBase: base, QPalette.ToolTipText: text, QPalette.Text: text, QPalette.Button: window,
        QPalette.ButtonText: text, QPalette.BrightText: QColor("#ff5c5c"), QPalette.Highlight: accent,
        QPalette.HighlightedText: QColor("white"), QPalette.Link: accent, QPalette.PlaceholderText: QColor("#808080"),
    }.items():
        pal.setColor(role, color)
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        pal.setColor(QPalette.Disabled, role, QColor("#6e6e6e"))
    app.setPalette(pal)
