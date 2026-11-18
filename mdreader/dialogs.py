"""对话框: 查找替换、插入表格、插入链接。"""
from __future__ import annotations

import re
from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                             QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QSpinBox, QVBoxLayout)

from .editor import MarkdownEditor


class _PosMap:
    """Python 字符串下标 <-> Qt 文档位置 (UTF-16) 互转。"""

    def __init__(self, text: str) -> None:
        if any(ord(c) > 0xFFFF for c in text):
            self.offs = [0]
            for ch in text:
                self.offs.append(self.offs[-1] + (2 if ord(ch) > 0xFFFF else 1))
        else:
            self.offs = None

    def to_qt(self, i: int) -> int:
        return self.offs[i] if self.offs else i

    def to_py(self, q: int) -> int:
        if not self.offs:
            return q
        import bisect
        return bisect.bisect_left(self.offs, q)


class FindReplaceDialog(QDialog):
    def __init__(self, parent, editor_getter: Callable[[], MarkdownEditor]) -> None:
        super().__init__(parent)
        self.setWindowTitle("查找和替换")
        self.editor = editor_getter
        self.find_edit = QLineEdit()
        self.replace_edit = QLineEdit()
        self.case_cb = QCheckBox("区分大小写")
        self.word_cb = QCheckBox("全字匹配")
        self.regex_cb = QCheckBox("正则表达式")
        self.wrap_cb = QCheckBox("循环查找")
        self.wrap_cb.setChecked(True)
        self.status = QLabel()
        self.status.setMinimumWidth(260)

        grid = QGridLayout()
        grid.addWidget(QLabel("查找内容:"), 0, 0)
        grid.addWidget(self.find_edit, 0, 1)
        grid.addWidget(QLabel("替换为:"), 1, 0)
        grid.addWidget(self.replace_edit, 1, 1)
        opts = QHBoxLayout()
        for cb in (self.case_cb, self.word_cb, self.regex_cb, self.wrap_cb):
            opts.addWidget(cb)
        opts.addStretch()
        grid.addLayout(opts, 2, 0, 1, 2)
        grid.addWidget(self.status, 3, 0, 1, 2)

        btns = QVBoxLayout()
        self.btn_next = QPushButton("查找下一个")
        self.btn_prev = QPushButton("查找上一个")
        self.btn_replace = QPushButton("替换")
        self.btn_all = QPushButton("全部替换")
        btn_close = QPushButton("关闭")
        for b in (self.btn_next, self.btn_prev, self.btn_replace, self.btn_all, btn_close):
            btns.addWidget(b)
        btns.addStretch()
        self.btn_next.setDefault(True)
        self.btn_next.clicked.connect(lambda: self.find(True))
        self.btn_prev.clicked.connect(lambda: self.find(False))
        self.btn_replace.clicked.connect(self.replace)
        self.btn_all.clicked.connect(self.replace_all)
        btn_close.clicked.connect(self.close)

        lay = QHBoxLayout(self)
        lay.addLayout(grid, 1)
        lay.addLayout(btns)
        self.resize(560, 170)

    def show_find(self, replace: bool) -> None:
        c = self.editor().textCursor()
        if c.hasSelection() and " " not in c.selectedText():
            self.find_edit.setText(c.selectedText())
        self.setWindowTitle("查找和替换" if replace else "查找")
        self.replace_edit.setVisible(True)
        self.show()
        self.raise_()
        self.activateWindow()
        (self.replace_edit if replace and self.find_edit.text() else self.find_edit).setFocus()
        self.find_edit.selectAll()

    # ------------------------------------------------------------------
    def _regex(self) -> Optional[re.Pattern]:
        pat = self.find_edit.text()
        if not pat:
            self.status.setText("请输入查找内容")
            return None
        if not self.regex_cb.isChecked():
            pat = re.escape(pat)
        if self.word_cb.isChecked():
            pat = rf"(?<!\w)(?:{pat})(?!\w)"
        flags = re.MULTILINE | (0 if self.case_cb.isChecked() else re.IGNORECASE)
        try:
            return re.compile(pat, flags)
        except re.error as e:
            self.status.setText(f"正则表达式错误: {e}")
            return None

    def has_pattern(self) -> bool:
        return bool(self.find_edit.text())

    def find(self, forward: bool = True) -> bool:
        rx = self._regex()
        if rx is None:
            return False
        ed = self.editor()
        text = ed.toPlainText()
        pm = _PosMap(text)
        c = ed.textCursor()
        m = None
        if forward:
            start = pm.to_py(c.selectionEnd())
            m = self._first(rx, text, start, len(text))
            if m is None and self.wrap_cb.isChecked():
                m = self._first(rx, text, 0, len(text))
        else:
            end = pm.to_py(c.selectionStart())
            m = self._last(rx, text, 0, end)
            if m is None and self.wrap_cb.isChecked():
                m = self._last(rx, text, 0, len(text))
        if m is None:
            self.status.setText("找不到 “%s”" % self.find_edit.text())
            return False
        cur = QTextCursor(ed.document())
        cur.setPosition(pm.to_qt(m.start()))
        cur.setPosition(pm.to_qt(m.end()), QTextCursor.MoveMode.KeepAnchor)
        ed.setTextCursor(cur)
        ed.centerCursor()
        total = sum(1 for x in rx.finditer(text) if x.end() > x.start())
        self.status.setText(f"共 {total} 处匹配")
        return True

    @staticmethod
    def _first(rx, text, start, end):
        for m in rx.finditer(text, start, end):
            if m.end() > m.start():
                return m
        return None

    @staticmethod
    def _last(rx, text, start, end):
        last = None
        for m in rx.finditer(text, start, end):
            if m.end() > m.start():
                last = m
        return last

    def _replacement(self, m: re.Match) -> str:
        r = self.replace_edit.text()
        if self.regex_cb.isChecked():
            try:
                return m.expand(r)
            except (re.error, IndexError):
                return r
        return r

    def replace(self) -> None:
        rx = self._regex()
        if rx is None:
            return
        ed = self.editor()
        c = ed.textCursor()
        sel = c.selectedText().replace(" ", "\n")
        if sel:
            m = rx.fullmatch(sel)
            if m:
                c.insertText(self._replacement(m))
        self.find(True)

    def replace_all(self) -> None:
        rx = self._regex()
        if rx is None:
            return
        ed = self.editor()
        text = ed.toPlainText()
        new, n = rx.subn(self._replacement, text)
        if n == 0:
            self.status.setText("找不到 “%s”" % self.find_edit.text())
            return
        pos = ed.textCursor().position()
        vs = ed.verticalScrollBar().value()
        c = QTextCursor(ed.document())
        c.beginEditBlock()
        c.select(QTextCursor.SelectionType.Document)
        c.insertText(new)
        c.endEditBlock()
        c.setPosition(min(pos, len(new)))
        ed.setTextCursor(c)
        ed.verticalScrollBar().setValue(vs)
        self.status.setText(f"已替换 {n} 处")


class InsertTableDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("插入表格")
        self.rows = QSpinBox()
        self.rows.setRange(1, 200)
        self.rows.setValue(3)
        self.cols = QSpinBox()
        self.cols.setRange(1, 30)
        self.cols.setValue(3)
        self.align = QComboBox()
        self.align.addItem("默认", None)
        self.align.addItem("左对齐", "left")
        self.align.addItem("居中", "center")
        self.align.addItem("右对齐", "right")
        form = QFormLayout(self)
        form.addRow("数据行数:", self.rows)
        form.addRow("列数:", self.cols)
        form.addRow("对齐方式:", self.align)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("插入")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)


class LinkDialog(QDialog):
    def __init__(self, parent=None, text: str = "", url: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("插入链接")
        self.text_edit = QLineEdit(text)
        self.url_edit = QLineEdit(url)
        self.url_edit.setPlaceholderText("https://   或   相对路径 / #标题锚点")
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("可选")
        form = QFormLayout(self)
        form.addRow("显示文字:", self.text_edit)
        form.addRow("链接地址:", self.url_edit)
        form.addRow("提示标题:", self.title_edit)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("插入")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        self.resize(460, 140)
        (self.url_edit if text else self.text_edit).setFocus()

    def markdown(self) -> str:
        text = self.text_edit.text() or self.url_edit.text()
        url = self.url_edit.text().strip()
        if " " in url:
            url = f"<{url}>"
        title = self.title_edit.text().strip()
        t = f' "{title}"' if title else ""
        return f"[{text}]({url}{t})"
