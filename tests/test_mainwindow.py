"""Smoke tests for the main window. Avoid code paths that open modal dialogs:
they would block a headless test run forever."""
import os

import pytest
from PyQt6.QtGui import QTextCursor

from mdreader import mainwindow as mw
from mdreader.fileio import read_text_file
from mdreader.themes import LIGHT
from tests.conftest import EXAMPLES


@pytest.fixture
def win(qapp):
    w = mw.MainWindow(initial_text="")
    yield w
    w.editor.document().setModified(False)
    w.close()


def open_window(path):
    return mw.MainWindow(str(path))


def select(w, start, end):
    c = w.editor.textCursor()
    c.setPosition(start)
    c.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    w.editor.setTextCursor(c)


def test_open_demo_renders_tables_and_images(qapp):
    w = open_window(os.path.join(EXAMPLES, "demo.md"))
    try:
        html = w.preview.document().toHtml()
        assert "<table" in html and "<img" in html
        assert w.file_path.endswith("demo.md")
        assert not w.editor.document().isModified()
    finally:
        w.close()


def test_bold_wraps_and_unwraps(win):
    win.editor.setPlainText("hello world")
    select(win, 0, 5)
    win.wrap_selection("**", "**", "粗体")
    assert win.editor.toPlainText() == "**hello** world"
    assert win.editor.textCursor().selectedText() == "hello"
    win.wrap_selection("**", "**", "粗体")
    assert win.editor.toPlainText() == "hello world"


def test_wrap_without_selection_inserts_placeholder(win):
    win.editor.setPlainText("")
    win.wrap_selection("`", "`", "code")
    assert win.editor.toPlainText() == "`code`"
    assert win.editor.textCursor().selectedText() == "code"


def test_heading_toggle(win):
    win.editor.setPlainText("Title")
    win.set_heading(2)
    assert win.editor.toPlainText() == "## Title"
    win.set_heading(3)
    assert win.editor.toPlainText() == "### Title"
    win.set_heading(3)
    assert win.editor.toPlainText() == "Title"


def test_list_prefix_toggle(win):
    win.editor.setPlainText("a\nb")
    select(win, 0, 3)
    win.toggle_prefix("", numbered=True)
    assert win.editor.toPlainText() == "1. a\n2. b"
    select(win, 0, len("1. a\n2. b"))
    win.toggle_prefix("- ")
    assert win.editor.toPlainText() == "- a\n- b"
    select(win, 0, len("- a\n- b"))
    win.toggle_prefix("- ")
    assert win.editor.toPlainText() == "a\nb"


def test_format_tables_command(win):
    win.editor.setPlainText("|a|bb|\n|-|-|\n|ccc|d|")
    win.format_tables()
    assert win.editor.toPlainText().split("\n")[0] == "| a   | bb  |"


def test_save_roundtrip_keeps_encoding(qapp, tmp_path):
    p = tmp_path / "gbk.md"
    p.write_bytes("# 你好\r\n".encode("gbk"))
    w = open_window(p)
    try:
        assert (w.encoding, w.newline) == ("gb18030", "\r\n")
        w.editor.setPlainText("# 你好\n世界\n")
        assert w.save()
        info = read_text_file(str(p))
        assert (info.encoding, info.newline, info.text) == ("gb18030", "\r\n", "# 你好\n世界\n")
    finally:
        w.close()


def test_export_pdf_embeds_images(qapp, tmp_path, png_file):
    md = tmp_path / "doc.md"
    md.write_text("# PDF\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n![p](pic.png)\n", encoding="utf-8")
    w = open_window(md)
    try:
        out = tmp_path / "doc.pdf"
        assert w.export_pdf(str(out), ask_open=False)
        data = out.read_bytes()
        assert data.startswith(b"%PDF")
        assert b"/Subtype /Image" in data or b"/Subtype/Image" in data
    finally:
        w.close()


def test_link_path_is_relative_and_bracketed(qapp, tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("", encoding="utf-8")
    w = open_window(md)
    try:
        assert w._make_link_path(str(tmp_path / "images" / "a.png")) == "images/a.png"
        assert w._make_link_path(str(tmp_path / "my pic.png")) == "<my pic.png>"
    finally:
        w.close()


def test_help_markdown_renders():
    html = mw.shared_renderer().render_qt(mw.help_markdown("x.png"), LIGHT)
    assert "<table" in html
