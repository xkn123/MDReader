"""Shared fixtures.

Runs Qt headless (offscreen platform) and redirects QSettings to a temp INI
file so tests never touch the real user settings in the Windows registry.
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")

_settings_dir = tempfile.mkdtemp(prefix="mdreader-test-settings-")
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _settings_dir)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("MDReaderTests")
    app.setApplicationName("MDReaderTests")
    yield app


@pytest.fixture
def png_file(tmp_path):
    """A 200x100 red PNG on disk; returns its path."""
    img = QImage(200, 100, QImage.Format.Format_RGB32)
    img.fill(QColor("red"))
    path = tmp_path / "pic.png"
    assert img.save(str(path), "PNG")
    return str(path)
