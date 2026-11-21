"""Markdown -> HTML. The Qt flavour must stay inside QTextBrowser's HTML subset."""
import re

import pytest

from mdreader.renderer import MarkdownRenderer, qt_stylesheet, slugify
from mdreader.themes import DARK, LIGHT


@pytest.fixture(scope="module")
def r():
    return MarkdownRenderer()


TABLE = "| a | b |\n|:-|-:|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n"


def test_qt_table_has_border_alignment_and_zebra_stripes(r):
    h = r.render_qt(TABLE, LIGHT)
    assert '<table border="1"' in h
    assert 'style="text-align:right' in h
    # stripes on even body rows only (row 2), set via td style
    assert h.count(f"background-color:{LIGHT.table_stripe}") == 2
    assert "<th" in h


def test_web_table_is_plain(r):
    h = r.render_web(TABLE)
    assert "<table>" in h and "border=" not in h
    assert "background-color" not in h


def test_qt_code_block_is_single_cell_table_with_highlighting(r):
    h = r.render_qt("```python\ndef f():\n    return 1\n```\n", LIGHT)
    assert h.startswith("<table") and f'bgcolor="{LIGHT.code_bg}"' in h
    assert "<pre" in h and "color:" in h          # Pygments inline styles
    assert "class=" not in h                      # no CSS classes in Qt mode


def test_unknown_language_is_escaped_not_dropped(r):
    h = r.render_qt("```nosuchlang\n<b>x</b>\n```\n", LIGHT)
    assert "&lt;b&gt;x&lt;/b&gt;" in h


def test_web_code_block_has_language_class(r):
    h = r.render_web("```js\nlet a = 1\n```\n")
    assert '<pre><code class="language-js">' in h


def test_qt_blockquote_is_two_cell_table(r):
    h = r.render_qt("> quoted\n", DARK)
    assert f'bgcolor="{DARK.quote_bar}"' in h
    assert "<blockquote" not in h


def test_task_lists(r):
    md = "- [x] done\n- [ ] todo\n"
    q = r.render_qt(md, LIGHT)
    assert "☑" in q and "☐" in q and "list-style-type:none" in q
    assert "[x]" not in q
    w = r.render_web(md)
    assert '<input type="checkbox" disabled checked>' in w
    assert 'class="contains-task-list"' in w


def test_heading_ids_become_named_anchors_in_qt(r):
    q = r.render_qt("# Hello World\n\n# Hello World\n\n## 中文 标题\n", LIGHT)
    assert '<a name="hello-world"></a>' in q
    assert '<a name="hello-world-1"></a>' in q
    assert '<a name="中文-标题"></a>' in q
    assert " id=" not in q
    w = r.render_web("# Hello World\n")
    assert 'id="hello-world"' in w


def test_inline_html_block_is_wrapped_in_paragraph(r):
    # Without the <p>, Qt merges the image into the previous paragraph.
    q = r.render_qt("text\n\n<img src=\"a.png\" width=\"300\">\n", LIGHT)
    assert '<p><img src="a.png" width="300">' in q


def test_rewrite_src_applies_to_markdown_and_html_images(r):
    md = '![x](a b.png)\n\n![y](<c d.png>)\n\n<img src="e.png">\n\ninline <img src="f.png"> img\n'
    seen = []

    def rw(s):
        seen.append(s)
        return "NEW/" + s

    w = r.render_web(md, rw)
    # markdown-it percent-encodes Markdown image URLs; ImageProvider.resolve unquotes them
    assert set(seen) >= {"c%20d.png", "e.png", "f.png"}
    assert 'src="NEW/e.png"' in w and 'src="NEW/f.png"' in w


def test_strikethrough_and_footnotes(r):
    w = r.render_web("~~old~~ text[^1]\n\n[^1]: note\n")
    assert "<s>old</s>" in w
    assert "footnote" in w


def test_export_html_is_complete_document(r):
    doc = r.export_html("# T\n", "my <title>")
    assert doc.startswith("<!DOCTYPE html>")
    assert "<title>my &lt;title&gt;</title>" in doc
    assert 'class="markdown-body"' in doc


def test_slugify_dedupes():
    used = set()
    assert [slugify(t, used) for t in ["A b", "A b", "!!", "!!"]] == ["a-b", "a-b-1", "section", "section-1"]


def test_stylesheet_scales_with_base_size():
    small, big = qt_stylesheet(LIGHT, 10), qt_stylesheet(LIGHT, 20)
    assert re.search(r"h1 \{ font-size:20pt", small)
    assert re.search(r"h1 \{ font-size:40pt", big)
