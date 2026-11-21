import pytest

from mdreader.dialogs import FindReplaceDialog, LinkDialog, _PosMap
from mdreader.editor import MarkdownEditor

EMOJI = "\U0001F600"


def test_posmap_converts_around_surrogates():
    pm = _PosMap("a" + EMOJI + "b")
    assert [pm.to_qt(i) for i in range(4)] == [0, 1, 3, 4]
    assert [pm.to_py(q) for q in (0, 1, 3, 4)] == [0, 1, 2, 3]
    plain = _PosMap("abc")
    assert plain.to_qt(2) == 2 and plain.to_py(2) == 2


@pytest.fixture
def fr(qapp):
    ed = MarkdownEditor()
    dlg = FindReplaceDialog(None, lambda: ed)
    yield ed, dlg
    dlg.deleteLater()
    ed.deleteLater()


def test_find_selects_correct_range_after_emoji(fr):
    ed, dlg = fr
    ed.setPlainText(f"{EMOJI} cat {EMOJI} cat")
    dlg.find_edit.setText("cat")
    assert dlg.find(True)
    c = ed.textCursor()
    assert c.selectedText() == "cat" and c.selectionStart() == 3
    assert dlg.find(True)
    assert ed.textCursor().selectionStart() == 10
    assert dlg.find(True)                         # wraps around
    assert ed.textCursor().selectionStart() == 3
    assert dlg.find(False)
    assert ed.textCursor().selectionStart() == 10


def test_find_options(fr):
    ed, dlg = fr
    ed.setPlainText("Cat category cat")
    dlg.find_edit.setText("cat")
    dlg.case_cb.setChecked(True)
    dlg.word_cb.setChecked(True)
    assert dlg.find(True)
    assert ed.textCursor().selectionStart() == 13
    dlg.find_edit.setText("dog")
    assert not dlg.find(True)


def test_replace_all_with_regex_groups_is_one_undo_step(fr):
    ed, dlg = fr
    ed.setPlainText("2024-01-02 and 2025-12-31")
    dlg.find_edit.setText(r"(\d+)-(\d+)-(\d+)")
    dlg.replace_edit.setText(r"\3/\2/\1")
    dlg.regex_cb.setChecked(True)
    dlg.replace_all()
    assert ed.toPlainText() == "02/01/2024 and 31/12/2025"
    ed.undo()
    assert ed.toPlainText() == "2024-01-02 and 2025-12-31"


def test_replace_single_then_moves_to_next(fr):
    ed, dlg = fr
    ed.setPlainText("a x a")
    dlg.find_edit.setText("a")
    dlg.replace_edit.setText("b")
    dlg.find(True)
    dlg.replace()
    assert ed.toPlainText() == "b x a"
    assert ed.textCursor().selectionStart() == 4


def test_invalid_regex_reports_error(fr):
    ed, dlg = fr
    ed.setPlainText("x")
    dlg.find_edit.setText("(")
    dlg.regex_cb.setChecked(True)
    assert not dlg.find(True)
    assert "正则" in dlg.status.text()


def test_link_dialog_markdown(qapp):
    d = LinkDialog(None, "文字", "a b.md")
    d.title_edit.setText("t")
    assert d.markdown() == '[文字](<a b.md> "t")'
