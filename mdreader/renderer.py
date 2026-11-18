"""Markdown -> HTML 渲染.

提供两种输出:
* Qt 风格 (render_qt): 针对 QTextBrowser 所支持的 HTML 子集做了适配,
  用于程序内预览、打印和导出 PDF。
* 标准网页风格 (render_web / export_html): 用于导出 HTML 文件, 在浏览器中查看。
"""
from __future__ import annotations

import html
import re
from typing import Callable, Optional

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.footnote import footnote_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.styles import get_all_styles
from pygments.util import ClassNotFound

from .themes import LIGHT, Theme

MONO_FONTS = "Consolas, 'Cascadia Mono', 'Courier New', monospace"
BODY_FONTS = "'Segoe UI', 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif"

TASK_RE = re.compile(r"^\[([ xX])\]\s+")
IMG_SRC_RE = re.compile(r"(<img\b[^>]*?\bsrc\s*=\s*)([\"'])(.*?)\2", re.I | re.S)
ID_ATTR_RE = re.compile(r"<(\w+)([^<>]*?)\s+id=\"([^\"]*)\"([^<>]*)>")

_AVAILABLE_STYLES = set(get_all_styles())
_formatters: dict[str, HtmlFormatter] = {}
_lexers: dict[str, object] = {}


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------
def _formatter(style: str) -> HtmlFormatter:
    if style not in _AVAILABLE_STYLES:
        style = "default"
    f = _formatters.get(style)
    if f is None:
        f = HtmlFormatter(noclasses=True, nowrap=True, style=style)
        _formatters[style] = f
    return f


def _lexer(lang: str):
    lang = lang.lower()
    if lang in _lexers:
        return _lexers[lang]
    try:
        lexer = get_lexer_by_name(lang, stripnl=False, ensurenl=False)
    except ClassNotFound:
        lexer = None
    _lexers[lang] = lexer
    return lexer


def highlight_code(code: str, lang: str, style: str) -> str:
    """返回已转义 / 已着色的代码 HTML (不含外层 pre)。"""
    lexer = _lexer(lang) if lang else None
    if lexer is None:
        return html.escape(code)
    try:
        return highlight(code, lexer, _formatter(style))
    except Exception:
        return html.escape(code)


def _fence_lang(token: Token) -> str:
    info = (token.info or "").strip()
    return info.split(maxsplit=1)[0] if info else ""


def slugify(text: str, used: set) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s)
    s = re.sub(r"\s", "-", s)
    base = s or "section"
    slug, n = base, 1
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


def _inline_text(token: Token) -> str:
    if not token.children:
        return token.content
    return "".join(c.content for c in token.children
                   if c.type in ("text", "code_inline", "html_inline"))


def _ids_to_anchors(text: str) -> str:
    """QTextBrowser 不支持用 id 作为锚点, 转成 <a name>。"""
    def repl(m: re.Match) -> str:
        tag, before, ident, after = m.groups()
        open_tag = f"<{tag}{before}{after}>"
        anchor = f'<a name="{ident}"></a>'
        if tag.lower() == "a":
            return anchor + open_tag
        return open_tag + anchor
    return ID_ATTR_RE.sub(repl, text)


# --------------------------------------------------------------------------
# 渲染规则 - Qt 预览
# --------------------------------------------------------------------------
def _qt_fence(self, tokens, idx, options, env):
    tok = tokens[idx]
    theme: Theme = env["theme"]
    lang = _fence_lang(tok) if tok.type == "fence" else ""
    code = tok.content.rstrip("\n")
    body = highlight_code(code, lang, theme.pygments_style).rstrip("\n")
    pt = env.get("code_pt", 10)
    return (
        f'<table width="100%" cellspacing="0" cellpadding="10" bgcolor="{theme.code_bg}" '
        f'style="margin-top:4px; margin-bottom:12px;">'
        f'<tr><td><pre style="font-family:{MONO_FONTS}; font-size:{pt}pt; '
        f'margin:0px;">{body}</pre></td></tr></table>\n'
    )


def _qt_blockquote_open(self, tokens, idx, options, env):
    theme: Theme = env["theme"]
    return (
        '<table width="100%" cellspacing="0" cellpadding="0" '
        'style="margin-top:4px; margin-bottom:12px;"><tr>'
        f'<td width="4" bgcolor="{theme.quote_bar}"></td>'
        f'<td style="padding-left:14px; padding-top:4px; color:{theme.quote_text};">\n'
    )


def _qt_blockquote_close(self, tokens, idx, options, env):
    return "</td></tr></table>\n"


def _qt_table_open(self, tokens, idx, options, env):
    theme: Theme = env["theme"]
    return (
        f'<table border="1" cellspacing="0" cellpadding="7" '
        f'style="border-collapse:collapse; border-style:solid; border-color:{theme.border}; '
        f'margin-top:4px; margin-bottom:14px;">\n'
    )


_INLINE_HTML_START = re.compile(
    r"^\s*<(img|a|span|b|i|em|strong|br|code|kbd|sub|sup|font|u|s|small|big|mark|del|ins)\b", re.I)


def _qt_html_block(self, tokens, idx, options, env):
    content = tokens[idx].content
    # 以行内元素开头的 HTML 块需要包进段落, 否则 Qt 会把它并入上一段
    if _INLINE_HTML_START.match(content):
        return f"<p>{content}</p>\n"
    return content


def _qt_hr(self, tokens, idx, options, env):
    theme: Theme = env["theme"]
    return (f'<table width="100%" cellspacing="0" cellpadding="0" style="margin-top:10px; '
            f'margin-bottom:10px;"><tr><td height="2" bgcolor="{theme.border}"></td></tr></table>\n')


# --------------------------------------------------------------------------
# 渲染规则 - 网页导出
# --------------------------------------------------------------------------
def _web_fence(self, tokens, idx, options, env):
    tok = tokens[idx]
    lang = _fence_lang(tok) if tok.type == "fence" else ""
    body = highlight_code(tok.content, lang, "default")
    cls = f' class="language-{html.escape(lang)}"' if lang else ""
    return f"<pre><code{cls}>{body}</code></pre>\n"


# --------------------------------------------------------------------------
# token 后处理 (标题锚点 / 任务列表 / 表格斑马纹 / 图片路径改写)
# --------------------------------------------------------------------------
def _postprocess(tokens: list[Token], env: dict) -> None:
    qt = env.get("qt", False)
    theme: Theme = env["theme"]
    rewrite: Optional[Callable[[str], str]] = env.get("rewrite_src")
    used: set = set()
    list_stack: list[Token] = []
    in_tbody, row = False, 0

    for i, t in enumerate(tokens):
        tt = t.type
        if tt == "heading_open" and i + 1 < len(tokens):
            t.attrSet("id", slugify(_inline_text(tokens[i + 1]), used))
        elif tt in ("bullet_list_open", "ordered_list_open"):
            list_stack.append(t)
        elif tt in ("bullet_list_close", "ordered_list_close"):
            if list_stack:
                list_stack.pop()
        elif tt == "tbody_open":
            in_tbody, row = True, 0
        elif tt == "tbody_close":
            in_tbody = False
        elif tt == "tr_open" and in_tbody:
            row += 1
        elif tt == "td_open" and qt and in_tbody and row % 2 == 0:
            style = t.attrGet("style") or ""
            t.attrSet("style", (style + ";" if style else "")
                      + f"background-color:{theme.table_stripe}")
        elif tt in ("html_block",) and rewrite:
            t.content = _rewrite_img_tags(t.content, rewrite)
        elif tt == "inline":
            # 任务列表
            if (i >= 2 and tokens[i - 1].type == "paragraph_open"
                    and tokens[i - 2].type == "list_item_open" and t.children
                    and t.children[0].type == "text"):
                m = TASK_RE.match(t.children[0].content)
                if m:
                    checked = m.group(1) in "xX"
                    t.children[0].content = t.children[0].content[m.end():]
                    box = Token("html_inline", "", 0)
                    if qt:
                        if checked:
                            box.content = f'<span style="color:{theme.check_color}">☑</span> '
                        else:
                            box.content = f'<span style="color:{theme.muted}">☐</span> '
                    else:
                        box.content = ('<input type="checkbox" disabled'
                                       + (" checked" if checked else "") + "> ")
                    t.children.insert(0, box)
                    tokens[i - 2].attrSet("class", "task-list-item")
                    if list_stack:
                        if qt:
                            list_stack[-1].attrSet("style", "list-style-type:none")
                        else:
                            list_stack[-1].attrSet("class", "contains-task-list")
            if rewrite and t.children:
                for c in t.children:
                    if c.type == "image":
                        src = c.attrGet("src")
                        if src:
                            c.attrSet("src", rewrite(str(src)))
                    elif c.type == "html_inline":
                        c.content = _rewrite_img_tags(c.content, rewrite)


def _rewrite_img_tags(text: str, rewrite: Callable[[str], str]) -> str:
    def repl(m: re.Match) -> str:
        new = rewrite(html.unescape(m.group(3)))
        return f"{m.group(1)}{m.group(2)}{html.escape(new, quote=True)}{m.group(2)}"
    return IMG_SRC_RE.sub(repl, text)


# --------------------------------------------------------------------------
# 样式表
# --------------------------------------------------------------------------
def qt_stylesheet(theme: Theme, base_pt: int) -> str:
    def pt(scale: float) -> int:
        return max(6, round(base_pt * scale))
    return f"""
body {{ color:{theme.text}; }}
p {{ margin-top:0px; margin-bottom:12px; }}
h1 {{ font-size:{pt(2.0)}pt; color:{theme.heading}; font-weight:600; margin-top:20px; margin-bottom:12px; }}
h2 {{ font-size:{pt(1.6)}pt; color:{theme.heading}; font-weight:600; margin-top:20px; margin-bottom:10px; }}
h3 {{ font-size:{pt(1.3)}pt; color:{theme.heading}; font-weight:600; margin-top:16px; margin-bottom:8px; }}
h4 {{ font-size:{pt(1.12)}pt; color:{theme.heading}; font-weight:600; margin-top:14px; margin-bottom:8px; }}
h5 {{ font-size:{pt(1.0)}pt; color:{theme.heading}; font-weight:600; margin-top:12px; margin-bottom:6px; }}
h6 {{ font-size:{pt(0.92)}pt; color:{theme.muted}; font-weight:600; margin-top:12px; margin-bottom:6px; }}
a {{ color:{theme.link}; text-decoration:none; }}
code {{ font-family:{MONO_FONTS}; font-size:{pt(0.92)}pt; background-color:{theme.inline_code_bg}; }}
pre {{ font-family:{MONO_FONTS}; }}
th {{ background-color:{theme.table_header_bg}; font-weight:600; }}
li {{ margin-bottom:4px; }}
ul, ol {{ margin-top:0px; margin-bottom:12px; }}
sup {{ font-size:{pt(0.75)}pt; }}
"""


WEB_CSS = """
:root { color-scheme: light; }
body { margin: 0; background: #fff; }
.markdown-body {
  box-sizing: border-box; max-width: 900px; margin: 0 auto; padding: 40px 32px;
  font-family: -apple-system, 'Segoe UI', 'Microsoft YaHei', 'PingFang SC', sans-serif;
  font-size: 16px; line-height: 1.65; color: #1f2328; word-wrap: break-word;
}
.markdown-body h1, .markdown-body h2 { padding-bottom: .3em; border-bottom: 1px solid #d8dee4; }
.markdown-body h1, .markdown-body h2, .markdown-body h3, .markdown-body h4,
.markdown-body h5, .markdown-body h6 { margin-top: 24px; margin-bottom: 16px; font-weight: 600; line-height: 1.25; }
.markdown-body h1 { font-size: 2em; } .markdown-body h2 { font-size: 1.5em; }
.markdown-body h3 { font-size: 1.25em; } .markdown-body h6 { color: #59636e; }
.markdown-body a { color: #0969da; text-decoration: none; }
.markdown-body a:hover { text-decoration: underline; }
.markdown-body img { max-width: 100%; box-sizing: content-box; }
.markdown-body code { font-family: Consolas, 'Cascadia Mono', monospace; font-size: 85%;
  padding: .2em .4em; background: rgba(175,184,193,.2); border-radius: 6px; }
.markdown-body pre { padding: 16px; overflow: auto; font-size: 85%; line-height: 1.45;
  background: #f6f8fa; border-radius: 6px; }
.markdown-body pre code { padding: 0; background: transparent; font-size: 100%; }
.markdown-body blockquote { margin: 0 0 16px; padding: 0 1em; color: #59636e; border-left: .25em solid #d0d7de; }
.markdown-body table { border-collapse: collapse; margin: 0 0 16px; display: block; width: max-content; max-width: 100%; overflow: auto; }
.markdown-body th, .markdown-body td { padding: 6px 13px; border: 1px solid #d0d7de; }
.markdown-body th { font-weight: 600; background: #f0f3f6; }
.markdown-body tbody tr:nth-child(2n) { background: #f6f8fa; }
.markdown-body hr { height: .25em; padding: 0; margin: 24px 0; background: #d0d7de; border: 0; }
.markdown-body ul.contains-task-list { list-style: none; padding-left: 1.2em; }
.markdown-body li.task-list-item input { margin: 0 .3em .25em -1.3em; vertical-align: middle; }
.markdown-body .footnotes { font-size: 85%; color: #59636e; }
@media print { .markdown-body { padding: 0; max-width: none; } }
"""


# --------------------------------------------------------------------------
# 渲染器
# --------------------------------------------------------------------------
class MarkdownRenderer:
    def __init__(self) -> None:
        self.md_qt = self._create(qt=True)
        self.md_web = self._create(qt=False)

    @staticmethod
    def _create(qt: bool) -> MarkdownIt:
        md = MarkdownIt("commonmark", {"html": True, "typographer": False})
        md.enable(["table", "strikethrough"])
        md.use(footnote_plugin)
        if qt:
            md.add_render_rule("fence", _qt_fence)
            md.add_render_rule("code_block", _qt_fence)
            md.add_render_rule("blockquote_open", _qt_blockquote_open)
            md.add_render_rule("blockquote_close", _qt_blockquote_close)
            md.add_render_rule("table_open", _qt_table_open)
            md.add_render_rule("hr", _qt_hr)
            md.add_render_rule("html_block", _qt_html_block)
        else:
            md.add_render_rule("fence", _web_fence)
            md.add_render_rule("code_block", _web_fence)
        return md

    def render_qt(self, text: str, theme: Theme, base_pt: int = 11) -> str:
        env = {"theme": theme, "qt": True, "code_pt": max(6, round(base_pt * 0.92))}
        tokens = self.md_qt.parse(text, env)
        _postprocess(tokens, env)
        body = self.md_qt.renderer.render(tokens, self.md_qt.options, env)
        return _ids_to_anchors(body)

    def render_web(self, text: str, rewrite_src: Optional[Callable[[str], str]] = None) -> str:
        env = {"theme": LIGHT, "qt": False, "rewrite_src": rewrite_src}
        tokens = self.md_web.parse(text, env)
        _postprocess(tokens, env)
        return self.md_web.renderer.render(tokens, self.md_web.options, env)

    def export_html(self, text: str, title: str,
                    rewrite_src: Optional[Callable[[str], str]] = None) -> str:
        body = self.render_web(text, rewrite_src)
        return (
            "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"<title>{html.escape(title)}</title>\n<style>{WEB_CSS}</style>\n</head>\n"
            f"<body>\n<article class=\"markdown-body\">\n{body}</article>\n</body>\n</html>\n"
        )


_shared: Optional[MarkdownRenderer] = None


def shared_renderer() -> MarkdownRenderer:
    global _shared
    if _shared is None:
        _shared = MarkdownRenderer()
    return _shared
