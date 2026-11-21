"""Editor behaviour. Positions are Qt (UTF-16) offsets, so emoji count as 2."""
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtTest import QTest

from mdreader.editor import MarkdownEditor, u16len
from mdreader.highlighter import MarkdownHighlighter
from mdreader.themes import LIGHT


@pytest.fixture
def ed(qapp):
    e = MarkdownEditor()
    e.set_theme(LIGHT)
    yield e
    e.deleteLater()


def put(ed, text, pos=None, anchor=None):
    """Set text; put the cursor at `pos` (default: end), selecting from `anchor` if given."""
    ed.setPlainText(text)
    end = u16len(text)
    pos = end if pos is None else pos
    c = ed.textCursor()
    if anchor is None:
        c.setPosition(pos)
    else:
        c.setPosition(anchor)
        c.setPosition(pos, QTextCursor.MoveMode.KeepAnchor)
    ed.setTextCursor(c)


def enter(ed):
    QTest.keyClick(ed, Qt.Key.Key_Return)


@pytest.mark.parametrize("before,after", [
    ("- item", "- item\n- "),
    ("  * item", "  * item\n  * "),
    ("3. item", "3. item\n4. "),
    ("9) item", "9) item\n10) "),
    ("- [x] done", "- [x] done\n- [ ] "),
    ("> quote", "> quote\n> "),
    ("    code", "    code\n    "),
    ("plain", "plain\n"),
])
def test_enter_continues_lists_quotes_and_indent(ed, before, after):
    put(ed, before)
    enter(ed)
    assert ed.toPlainText() == after


def test_enter_on_empty_item_ends_list(ed):
    put(ed, "- a\n- ")
    enter(ed)
    assert ed.toPlainText() == "- a\n"


def test_enter_inside_marker_is_plain_newline(ed):
    put(ed, "- item", pos=1)
    enter(ed)
    assert ed.toPlainText() == "-\n item"


def test_tab_and_shift_tab_indent_selected_lines(ed):
    put(ed, "a\nb\nc", pos=3, anchor=0)  # lines a and b
    QTest.keyClick(ed, Qt.Key.Key_Tab)
    assert ed.toPlainText() == "    a\n    b\nc"
    QTest.keyClick(ed, Qt.Key.Key_Backtab)
    assert ed.toPlainText() == "a\nb\nc"


def test_tab_at_list_marker_indents_item(ed):
    put(ed, "- item", pos=2)
    QTest.keyClick(ed, Qt.Key.Key_Tab)
    assert ed.toPlainText() == "    - item"


def test_move_lines_with_emoji_keeps_selection(ed):
    put(ed, "\U0001F600a\nb\nc", pos=1, anchor=0)
    ed.move_lines(+1)
    assert ed.toPlainText() == "b\n\U0001F600a\nc"
    c = ed.textCursor()
    assert (c.anchor(), c.position()) == (2, 3)
    ed.move_lines(-1)
    assert ed.toPlainText() == "\U0001F600a\nb\nc"
    ed.move_lines(-1)                       # already at the top: no-op
    assert ed.toPlainText() == "\U0001F600a\nb\nc"


def test_duplicate_and_delete_line(ed):
    put(ed, "one\ntwo", pos=1)
    ed.duplicate_line()
    assert ed.toPlainText() == "one\none\ntwo"
    ed.delete_line()
    assert ed.toPlainText() == "one\ntwo"


def test_delete_last_line(ed):
    put(ed, "a\nb")
    ed.delete_line()
    assert ed.toPlainText() == "a"


def test_duplicate_multiline_selection(ed):
    put(ed, "a\nb", anchor=0)
    ed.duplicate_line()
    assert ed.toPlainText() == "a\nba\nb"


def test_highlighter_tracks_code_fence_state(ed):
    hl = MarkdownHighlighter(ed.document(), LIGHT)  # keep a reference or it is GC'd
    ed.setPlainText("text\n```\n# not heading\n```\n# heading")
    doc = ed.document()
    states = [doc.findBlockByNumber(i).userState() for i in range(5)]
    assert states[1] == 1 and states[2] == 1   # inside the fence
    assert states[4] != 1
    del hl
