"""编辑器中的 Markdown 语法高亮。"""
from __future__ import annotations

import re

from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from .themes import Theme

FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}(\s.*)?$")
QUOTE_RE = re.compile(r"^\s{0,3}>.*$")
LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])(?=\s)")
TASK_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(\[[ xX]\])")
HR_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")
FOOTNOTE_DEF_RE = re.compile(r"^\s{0,3}\[\^[^\]]+\]:")

BOLD_RE = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
ITALIC_RE = re.compile(r"(?<![\*\w\\])(\*|_)(?![\s\*_])(.+?)(?<![\s\\])\1(?![\*\w])")
STRIKE_RE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
HTML_RE = re.compile(r"</?[A-Za-z][^>]*>|<!--.*?-->")
LINK_RE = re.compile(r"(!?\[)([^\]]*)(\]\()([^)]*)(\))")
REF_LINK_RE = re.compile(r"!?\[[^\]]*\]\[[^\]]*\]|\[\^[^\]]+\]")
AUTOLINK_RE = re.compile(r"<https?://[^>\s]+>|https?://[^\s)<>]+")
CODE_RE = re.compile(r"(`+)(.+?)\1")


class MarkdownHighlighter(QSyntaxHighlighter):
    def __init__(self, document, theme: Theme) -> None:
        super().__init__(document)
        self.set_theme(theme, rehighlight=False)

    @staticmethod
    def _fmt(color: str, bold=False, italic=False, bg: str | None = None,
             strike=False, size_delta: float = 0) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if bold:
            f.setFontWeight(QFont.Weight.Bold)
        if italic:
            f.setFontItalic(True)
        if strike:
            f.setFontStrikeOut(True)
        if bg:
            f.setBackground(QColor(bg))
        return f

    def set_theme(self, theme: Theme, rehighlight: bool = True) -> None:
        t = theme
        self.f_heading = self._fmt(t.hl_heading, bold=True)
        self.f_quote = self._fmt(t.hl_quote, italic=True)
        self.f_list = self._fmt(t.hl_list, bold=True)
        self.f_task = self._fmt(t.hl_list)
        self.f_hr = self._fmt(t.hl_hr, bold=True)
        self.f_table = self._fmt(t.hl_table)
        self.f_bold = self._fmt(t.hl_emphasis, bold=True)
        self.f_italic = self._fmt(t.hl_emphasis, italic=True)
        self.f_strike = self._fmt(t.hl_strike, strike=True)
        self.f_html = self._fmt(t.hl_html)
        self.f_link = self._fmt(t.hl_link)
        self.f_url = self._fmt(t.hl_url)
        self.f_code = self._fmt(t.hl_code, bg=t.hl_code_bg)
        self.f_fence = self._fmt(t.hl_code)
        self.f_fence_marker = self._fmt(t.hl_code, bold=True)
        if rehighlight:
            self.rehighlight()

    # ------------------------------------------------------------------
    def highlightBlock(self, text: str) -> None:
        # Python 下标 -> UTF-16 下标 (仅在出现非 BMP 字符时需要转换)
        if any(ord(ch) > 0xFFFF for ch in text):
            offs = [0]
            for ch in text:
                offs.append(offs[-1] + (2 if ord(ch) > 0xFFFF else 1))
        else:
            offs = None

        def setf(start: int, end: int, fmt: QTextCharFormat) -> None:
            if offs is not None:
                start, end = offs[start], offs[end]
            if end > start:
                self.setFormat(start, end - start, fmt)

        in_fence = self.previousBlockState() == 1
        fence = FENCE_RE.match(text)
        if in_fence:
            if fence and not text.strip().strip("`~"):
                setf(0, len(text), self.f_fence_marker)
                self.setCurrentBlockState(0)
            else:
                setf(0, len(text), self.f_fence)
                self.setCurrentBlockState(1)
            return
        if fence:
            setf(0, len(text), self.f_fence_marker)
            self.setCurrentBlockState(1)
            return
        self.setCurrentBlockState(0)

        if HEADING_RE.match(text):
            setf(0, len(text), self.f_heading)
            return
        if HR_RE.match(text):
            setf(0, len(text), self.f_hr)
            return
        if TABLE_SEP_RE.match(text):
            setf(0, len(text), self.f_table)
            return
        if QUOTE_RE.match(text):
            setf(0, len(text), self.f_quote)
        m = LIST_RE.match(text)
        if m:
            setf(0, m.end(), self.f_list)
            tm = TASK_RE.match(text)
            if tm:
                setf(tm.start(1), tm.end(1), self.f_task)
        m = FOOTNOTE_DEF_RE.match(text)
        if m:
            setf(0, m.end(), self.f_link)
        if "|" in text and (text.lstrip().startswith("|") or text.count("|") >= 2):
            for i, ch in enumerate(text):
                if ch == "|":
                    setf(i, i + 1, self.f_table)

        for rx, fmt in ((BOLD_RE, self.f_bold), (ITALIC_RE, self.f_italic),
                        (STRIKE_RE, self.f_strike), (HTML_RE, self.f_html),
                        (REF_LINK_RE, self.f_link), (AUTOLINK_RE, self.f_url)):
            for mm in rx.finditer(text):
                setf(mm.start(), mm.end(), fmt)
        for mm in LINK_RE.finditer(text):
            setf(mm.start(1), mm.end(3), self.f_link)
            setf(mm.start(4), mm.end(4), self.f_url)
            setf(mm.start(5), mm.end(5), self.f_link)
        for mm in CODE_RE.finditer(text):
            setf(mm.start(), mm.end(), self.f_code)
