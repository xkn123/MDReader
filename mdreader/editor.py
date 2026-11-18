"""带行号、智能列表续写、图片粘贴 / 拖放的 Markdown 文本编辑器。"""
from __future__ import annotations

import os
import re
from typing import Callable, Optional

from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QPainter, QTextCursor,
                         QTextFormat)
from PyQt6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from .images import IMAGE_EXTS
from .themes import Theme

MD_EXTS = {".md", ".markdown", ".mdown", ".mkd", ".mkdn", ".txt"}
LIST_RE = re.compile(r"^(\s*)(?:([-*+])|(\d+)([.)]))(\s+)(\[[ xX]\]\s+)?")
QUOTE_RE = re.compile(r"^(\s*(?:>\s?)+)")


def u16len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


class _Gutter(QWidget):
    def __init__(self, editor: "MarkdownEditor") -> None:
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event) -> None:
        self.editor.paint_gutter(event)


class MarkdownEditor(QPlainTextEdit):
    filesDropped = pyqtSignal(list)
    zoomRequested = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.theme: Optional[Theme] = None
        self.show_line_numbers = True
        self.tab_size = 4
        self.image_saver: Optional[Callable[[QImage], Optional[str]]] = None
        self.link_maker: Optional[Callable[[str], str]] = None
        self._gutter = _Gutter(self)
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_gutter_width()

    # ------------------------------------------------------------------ 外观
    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.setStyleSheet(
            f"QPlainTextEdit {{ background-color:{theme.ed_bg}; color:{theme.ed_text};"
            f" selection-background-color:{theme.ed_selection};"
            f" selection-color:{theme.ed_selection_text}; border:none; }}")
        self._highlight_current_line()
        self._gutter.update()

    def set_editor_font(self, font: QFont) -> None:
        self.setFont(font)
        self.document().setDefaultFont(font)
        self.setTabStopDistance(QFontMetricsF(font).horizontalAdvance(" ") * self.tab_size)
        self._update_gutter_width()

    def set_line_numbers(self, on: bool) -> None:
        self.show_line_numbers = on
        self._gutter.setVisible(on)
        self._update_gutter_width()

    def gutter_width(self) -> int:
        if not self.show_line_numbers:
            return 0
        digits = max(3, len(str(max(1, self.blockCount()))))
        return 18 + int(self.fontMetrics().horizontalAdvance("9") * digits)

    def _update_gutter_width(self, *_):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _update_gutter(self, rect: QRect, dy: int) -> None:
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        cr = self.contentsRect()
        self._gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def paint_gutter(self, event) -> None:
        if not self.show_line_numbers or self.theme is None:
            return
        p = QPainter(self._gutter)
        p.fillRect(event.rect(), QColor(self.theme.ed_gutter_bg))
        p.setFont(self.font())
        block = self.firstVisibleBlock()
        num = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        current = self.textCursor().blockNumber()
        h = self.fontMetrics().height()
        w = self._gutter.width() - 8
        fg, active = QColor(self.theme.ed_gutter_fg), QColor(self.theme.ed_gutter_active)
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                p.setPen(active if num == current else fg)
                p.drawText(0, top, w, h, Qt.AlignmentFlag.AlignRight, str(num + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            num += 1
        p.end()

    def _highlight_current_line(self) -> None:
        if self.theme is None:
            return
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(QColor(self.theme.ed_current_line))
        sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        sel.cursor = self.textCursor()
        sel.cursor.clearSelection()
        self.setExtraSelections([sel])
        self._gutter.update()

    # ------------------------------------------------------------------ 键盘
    def keyPressEvent(self, e) -> None:
        key, mods = e.key(), e.modifiers()
        plain = not (mods & (Qt.KeyboardModifier.ShiftModifier
                             | Qt.KeyboardModifier.ControlModifier
                             | Qt.KeyboardModifier.AltModifier))
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and plain:
            if self._smart_newline():
                return
        elif key == Qt.Key.Key_Tab and plain:
            c = self.textCursor()
            multi = c.hasSelection() and (
                self.document().findBlock(c.selectionStart()).blockNumber()
                != self.document().findBlock(c.selectionEnd()).blockNumber())
            if multi or (not c.hasSelection() and LIST_RE.match(c.block().text())
                         and c.positionInBlock() <= u16len(LIST_RE.match(c.block().text()).group(0))):
                self.indent_lines()
            else:
                c.insertText(" " * self.tab_size)
            return
        elif key == Qt.Key.Key_Backtab:
            self.outdent_lines()
            return
        super().keyPressEvent(e)

    def _smart_newline(self) -> bool:
        c = self.textCursor()
        if c.hasSelection():
            return False
        text = c.block().text()
        col = c.positionInBlock()
        m = LIST_RE.match(text)
        if m:
            if u16len(text[:m.end()]) > col:
                return False
            if not text[m.end():].strip() and c.atBlockEnd():
                # 空列表项 -> 结束列表
                c.beginEditBlock()
                c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                c.removeSelectedText()
                c.endEditBlock()
                self.setTextCursor(c)
                return True
            indent = m.group(1)
            marker = m.group(2) if m.group(2) else f"{int(m.group(3)) + 1}{m.group(4)}"
            task = "[ ] " if m.group(6) else ""
            c.insertText("\n" + indent + marker + " " + task)
            self.ensureCursorVisible()
            return True
        q = QUOTE_RE.match(text)
        if q and text.strip():
            if u16len(q.group(1)) > col:
                return False
            if not text[q.end():].strip() and c.atBlockEnd():
                c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                c.removeSelectedText()
                self.setTextCursor(c)
                return True
            c.insertText("\n" + q.group(1))
            self.ensureCursorVisible()
            return True
        ind = re.match(r"^[ \t]*", text).group(0)
        if ind and col >= len(ind):
            c.insertText("\n" + ind)
            self.ensureCursorVisible()
            return True
        return False

    # ------------------------------------------------------------------ 行操作
    def selected_blocks(self):
        c = self.textCursor()
        doc = self.document()
        start = doc.findBlock(c.selectionStart())
        end = doc.findBlock(c.selectionEnd())
        if c.hasSelection() and end.blockNumber() > start.blockNumber() \
                and c.selectionEnd() == end.position():
            end = end.previous()
        blocks, b = [], start
        while b.isValid():
            blocks.append(b)
            if b.blockNumber() >= end.blockNumber():
                break
            b = b.next()
        return blocks

    def transform_lines(self, func: Callable[[list[str]], list[str]], select=True) -> None:
        blocks = self.selected_blocks()
        first = blocks[0].position()
        last = blocks[-1].position() + blocks[-1].length() - 1
        old = [b.text() for b in blocks]
        new = func(old)
        if new == old:
            return
        c = QTextCursor(self.document())
        c.beginEditBlock()
        c.setPosition(first)
        c.setPosition(last, QTextCursor.MoveMode.KeepAnchor)
        joined = "\n".join(new)
        c.insertText(joined)
        c.endEditBlock()
        if select and len(blocks) > 1:
            c.setPosition(first)
            c.setPosition(first + u16len(joined), QTextCursor.MoveMode.KeepAnchor)
        else:
            c.setPosition(first + u16len(joined))
        self.setTextCursor(c)

    def indent_lines(self) -> None:
        pad = " " * self.tab_size
        self.transform_lines(lambda ls: [pad + l if l.strip() or len(ls) == 1 else l for l in ls])

    def outdent_lines(self) -> None:
        n = self.tab_size

        def out(ls):
            res = []
            for l in ls:
                if l.startswith("\t"):
                    res.append(l[1:])
                else:
                    k = len(l) - len(l.lstrip(" "))
                    res.append(l[min(k, n):])
            return res
        self.transform_lines(out)

    def duplicate_line(self) -> None:
        c = self.textCursor()
        if c.hasSelection():
            t = c.selectedText()
            c.setPosition(c.selectionEnd())
            c.insertText(t.replace(" ", "\n"))
            return
        text = c.block().text()
        c.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        c.insertText("\n" + text)
        self.setTextCursor(c)

    def delete_line(self) -> None:
        blocks = self.selected_blocks()
        c = QTextCursor(self.document())
        c.beginEditBlock()
        c.setPosition(blocks[0].position())
        end = blocks[-1].position() + blocks[-1].length()
        if end > self.document().characterCount() - 1:
            end = self.document().characterCount() - 1
            if blocks[0].position() > 0:
                c.setPosition(blocks[0].position() - 1)
        c.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        c.removeSelectedText()
        c.endEditBlock()
        self.setTextCursor(c)

    def move_lines(self, direction: int) -> None:
        blocks = self.selected_blocks()
        first, last = blocks[0], blocks[-1]
        other = first.previous() if direction < 0 else last.next()
        if not other.isValid():
            return
        c = self.textCursor()
        first_pos = first.position()
        anchor_off = c.anchor() - first_pos
        pos_off = c.position() - first_pos
        lines = [b.text() for b in blocks]
        o_text = other.text()
        if direction < 0:
            start = other.position()
            end = last.position() + last.length() - 1
            new = lines + [o_text]
            new_first = start
        else:
            start = first_pos
            end = other.position() + other.length() - 1
            new = [o_text] + lines
            new_first = first_pos + u16len(o_text) + 1
        cur = QTextCursor(self.document())
        cur.beginEditBlock()
        cur.setPosition(start)
        cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cur.insertText("\n".join(new))
        cur.endEditBlock()
        c = QTextCursor(self.document())
        c.setPosition(new_first + anchor_off)
        c.setPosition(new_first + pos_off, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(c)

    # ------------------------------------------------------------------ 鼠标
    def wheelEvent(self, e) -> None:
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoomRequested.emit(1 if e.angleDelta().y() > 0 else -1)
            e.accept()
            return
        super().wheelEvent(e)

    # ------------------------------------------------------------------ 粘贴 / 拖放
    def canInsertFromMimeData(self, source) -> bool:
        return source.hasImage() or source.hasUrls() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source) -> None:
        if source.hasUrls() and all(u.isLocalFile() for u in source.urls()):
            parts, to_open = [], []
            for url in source.urls():
                path = url.toLocalFile()
                ext = os.path.splitext(path)[1].lower()
                name = os.path.splitext(os.path.basename(path))[0]
                link = self.link_maker(path) if self.link_maker else path.replace("\\", "/")
                if ext in IMAGE_EXTS:
                    parts.append(f"![{name}]({link})")
                elif ext in MD_EXTS:
                    to_open.append(path)
                else:
                    parts.append(f"[{os.path.basename(path)}]({link})")
            if to_open:
                self.filesDropped.emit(to_open)
            if parts:
                self.textCursor().insertText("\n".join(parts))
            return
        if source.hasImage() and not source.hasText():
            img = QImage(source.imageData())
            if not img.isNull() and self.image_saver:
                md = self.image_saver(img)
                if md:
                    self.textCursor().insertText(md)
            return
        if source.hasText():
            self.textCursor().insertText(source.text())
            return
        super().insertFromMimeData(source)
