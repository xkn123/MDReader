"""程序入口。"""
from __future__ import annotations

import os
import sys

from PyQt6.QtCore import QLibraryInfo, QLocale, QTranslator
from PyQt6.QtWidgets import QApplication

from . import APP_NAME
from .icon import app_icon
from .themes import apply_app_theme


def _install_translations(app: QApplication) -> None:
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    candidates = [path]
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        candidates.insert(0, os.path.join(base, "PyQt6", "Qt6", "translations"))
    for folder in candidates:
        tr = QTranslator(app)
        if tr.load(QLocale("zh_CN"), "qtbase", "_", folder):
            app.installTranslator(tr)
            app._mdr_translator = tr  # 保持引用
            return


def run(argv: list[str]) -> int:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MDReader.MarkdownEditor")
        except Exception:
            pass

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setWindowIcon(app_icon())
    _install_translations(app)

    from .mainwindow import MainWindow, current_theme
    apply_app_theme(current_theme())

    files = [a for a in argv[1:] if not a.startswith("-") and os.path.isfile(a)]
    if files:
        first = MainWindow(files[0])
        first.show()
        for f in files[1:]:
            first.open_path(f)
    else:
        MainWindow().show()
    return app.exec()
