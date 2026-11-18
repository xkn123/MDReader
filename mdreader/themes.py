"""浅色 / 深色主题配色."""
from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication


@dataclass(frozen=True)
class Theme:
    name: str
    dark: bool
    # ---- 预览 ----
    text: str
    background: str
    link: str
    heading: str
    muted: str
    border: str
    code_bg: str
    inline_code_bg: str
    table_header_bg: str
    table_stripe: str
    quote_bar: str
    quote_text: str
    check_color: str
    pygments_style: str
    # ---- 编辑器 ----
    ed_bg: str
    ed_text: str
    ed_current_line: str
    ed_gutter_bg: str
    ed_gutter_fg: str
    ed_gutter_active: str
    ed_selection: str
    ed_selection_text: str
    # ---- 语法高亮 ----
    hl_heading: str
    hl_emphasis: str
    hl_code: str
    hl_code_bg: str
    hl_link: str
    hl_url: str
    hl_list: str
    hl_quote: str
    hl_html: str
    hl_table: str
    hl_hr: str
    hl_strike: str


LIGHT = Theme(
    name="light", dark=False,
    text="#1f2328", background="#ffffff", link="#0969da", heading="#1f2328",
    muted="#59636e", border="#d0d7de", code_bg="#f6f8fa", inline_code_bg="#eceff2",
    table_header_bg="#eef1f4", table_stripe="#f6f8fa", quote_bar="#d0d7de",
    quote_text="#59636e", check_color="#1a7f37", pygments_style="default",
    ed_bg="#ffffff", ed_text="#24292f", ed_current_line="#f2f6fb",
    ed_gutter_bg="#f6f8fa", ed_gutter_fg="#8c959f", ed_gutter_active="#24292f",
    ed_selection="#b6d6fd", ed_selection_text="#000000",
    hl_heading="#0550ae", hl_emphasis="#24292f", hl_code="#953800",
    hl_code_bg="#f3f4f6", hl_link="#0969da", hl_url="#6e7781", hl_list="#cf222e",
    hl_quote="#57606a", hl_html="#116329", hl_table="#8250df", hl_hr="#8c959f",
    hl_strike="#6e7781",
)

DARK = Theme(
    name="dark", dark=True,
    text="#e6edf3", background="#0d1117", link="#4493f8", heading="#f0f6fc",
    muted="#9198a1", border="#3d444d", code_bg="#161b22", inline_code_bg="#2a313c",
    table_header_bg="#1c2330", table_stripe="#151b23", quote_bar="#3d444d",
    quote_text="#9198a1", check_color="#3fb950", pygments_style="github-dark",
    ed_bg="#1e1e1e", ed_text="#d4d4d4", ed_current_line="#2a2d2e",
    ed_gutter_bg="#1e1e1e", ed_gutter_fg="#6e7681", ed_gutter_active="#c6c6c6",
    ed_selection="#264f78", ed_selection_text="#ffffff",
    hl_heading="#569cd6", hl_emphasis="#e8e8e8", hl_code="#ce9178",
    hl_code_bg="#2a2a2a", hl_link="#4fc1ff", hl_url="#808080", hl_list="#d7ba7d",
    hl_quote="#6a9955", hl_html="#4ec9b0", hl_table="#c586c0", hl_hr="#808080",
    hl_strike="#808080",
)

THEMES = {"light": LIGHT, "dark": DARK}

_default_style_name = None


def apply_app_theme(theme: Theme) -> None:
    """给整个应用设置窗口部件配色 (菜单、对话框等)."""
    global _default_style_name
    app = QApplication.instance()
    if app is None:
        return
    if _default_style_name is None:
        _default_style_name = app.style().name()

    try:
        app.styleHints().setColorScheme(
            Qt.ColorScheme.Dark if theme.dark else Qt.ColorScheme.Light)
    except Exception:  # 旧版 Qt 没有 setColorScheme
        pass

    if theme.dark:
        app.setStyle("Fusion")
        pal = QPalette()
        c = QColor
        pal.setColor(QPalette.ColorRole.Window, c("#202124"))
        pal.setColor(QPalette.ColorRole.WindowText, c("#e8eaed"))
        pal.setColor(QPalette.ColorRole.Base, c("#1e1e1e"))
        pal.setColor(QPalette.ColorRole.AlternateBase, c("#2a2a2a"))
        pal.setColor(QPalette.ColorRole.ToolTipBase, c("#2d2d30"))
        pal.setColor(QPalette.ColorRole.ToolTipText, c("#e8eaed"))
        pal.setColor(QPalette.ColorRole.Text, c("#e8eaed"))
        pal.setColor(QPalette.ColorRole.Button, c("#2d2e31"))
        pal.setColor(QPalette.ColorRole.ButtonText, c("#e8eaed"))
        pal.setColor(QPalette.ColorRole.BrightText, c("#ff6b6b"))
        pal.setColor(QPalette.ColorRole.Link, c("#4493f8"))
        pal.setColor(QPalette.ColorRole.Highlight, c("#264f78"))
        pal.setColor(QPalette.ColorRole.HighlightedText, c("#ffffff"))
        pal.setColor(QPalette.ColorRole.PlaceholderText, c("#8a8f98"))
        for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                     QPalette.ColorRole.ButtonText):
            pal.setColor(QPalette.ColorGroup.Disabled, role, c("#6b6f76"))
        app.setPalette(pal)
    else:
        app.setStyle(_default_style_name)
        app.setPalette(app.style().standardPalette())
