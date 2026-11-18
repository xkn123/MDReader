"""Markdown 表格格式化 (按显示宽度对齐列, 支持中文全角字符)。"""
from __future__ import annotations

import re
import unicodedata

SEP_CELL_RE = re.compile(r"^\s*:?-+:?\s*$")
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


def display_width(s: str) -> int:
    w = 0
    for ch in s:
        if unicodedata.combining(ch):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, buf, in_code, i = [], "", False, 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            buf += s[i:i + 2]
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            cells.append(buf)
            buf = ""
        else:
            buf += ch
        i += 1
    cells.append(buf)
    return [c.strip() for c in cells]


def is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(SEP_CELL_RE.match(c) for c in cells)


def _pad(text: str, width: int, align: str | None) -> str:
    extra = max(0, width - display_width(text))
    if align == "right":
        return " " * extra + text
    if align == "center":
        left = extra // 2
        return " " * left + text + " " * (extra - left)
    return text + " " * extra


def format_table(lines: list[str]) -> list[str] | None:
    if len(lines) < 2:
        return None
    rows = [split_row(l) for l in lines]
    if not is_separator(rows[1]):
        return None
    indent = re.match(r"^\s*", lines[0]).group(0)
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    aligns: list[str | None] = []
    for c in rows[1]:
        c = c.strip()
        left, right = c.startswith(":"), c.endswith(":") and len(c) > 1
        aligns.append("center" if left and right else "right" if right else "left" if left else None)
    widths = [3] * ncol
    for ri, r in enumerate(rows):
        if ri == 1:
            continue
        for ci, c in enumerate(r):
            widths[ci] = max(widths[ci], display_width(c))
    out = []
    for ri, r in enumerate(rows):
        if ri == 1:
            cells = []
            for w, a in zip(widths, aligns):
                if a == "center":
                    cells.append(":" + "-" * (w - 2) + ":")
                elif a == "right":
                    cells.append("-" * (w - 1) + ":")
                elif a == "left":
                    cells.append(":" + "-" * (w - 1))
                else:
                    cells.append("-" * w)
        else:
            cells = [_pad(c, w, a) for c, w, a in zip(r, widths, aligns)]
        out.append(indent + "| " + " | ".join(cells) + " |")
    return out


def find_tables(lines: list[str]) -> list[tuple[int, int]]:
    """返回所有表格的 (起始行, 结束行(不含)) 范围, 跳过代码块。"""
    result, i, in_fence = [], 0, False
    n = len(lines)
    while i < n:
        if FENCE_RE.match(lines[i]):
            in_fence = not in_fence
            i += 1
            continue
        if not in_fence and "|" in lines[i] and i + 1 < n \
                and is_separator(split_row(lines[i + 1])) and "|" in lines[i + 1]:
            j = i + 2
            while j < n and lines[j].strip() and "|" in lines[j]:
                j += 1
            result.append((i, j))
            i = j
            continue
        i += 1
    return result


def format_all_tables(text: str) -> tuple[str, int]:
    lines = text.split("\n")
    count = 0
    for start, end in reversed(find_tables(lines)):
        new = format_table(lines[start:end])
        if new:
            lines[start:end] = new
            count += 1
    return "\n".join(lines), count


def make_table(rows: int, cols: int, align: str | None = None) -> str:
    header = [f"列{i + 1}" for i in range(cols)]
    sep = {"left": ":---", "center": ":---:", "right": "---:"}.get(align or "", "---")
    lines = ["| " + " | ".join(header) + " |",
             "| " + " | ".join([sep] * cols) + " |"]
    for _ in range(rows):
        lines.append("| " + " | ".join(["   "] * cols) + " |")
    return "\n".join(format_table(lines) or lines)
