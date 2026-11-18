"""主窗口。"""
from __future__ import annotations

import base64
import datetime
import mimetypes
import os
import re
import tempfile
from urllib.parse import quote, unquote

from PyQt6.QtCore import (QFileSystemWatcher, QMarginsF, QSettings, QSize, Qt, QTimer, QUrl)
from PyQt6.QtGui import (QAction, QActionGroup, QDesktopServices, QFont, QFontDatabase,
                         QKeySequence, QPageLayout, QPageSize, QTextCursor)
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter, QPrintPreviewDialog
from PyQt6.QtWidgets import (QApplication, QFileDialog, QFontDialog, QInputDialog, QLabel,
                             QMainWindow, QMessageBox, QSplitter, QStyle, QToolBar)

from . import APP_NAME, APP_TITLE, __version__
from .dialogs import FindReplaceDialog, InsertTableDialog, LinkDialog
from .editor import MD_EXTS, MarkdownEditor, u16len
from .fileio import TextFileInfo, encoding_label, read_text_file, write_text_file
from .highlighter import MarkdownHighlighter
from .images import IMAGE_EXTS, WIN_ABS_RE, ImageProvider
from .preview import PreviewBrowser, RenderDocument, body_font
from .renderer import qt_stylesheet, shared_renderer
from .tableformat import find_tables, format_all_tables, format_table, make_table
from .themes import DARK, LIGHT, THEMES, Theme, apply_app_theme

MD_FILTER = ("Markdown 文件 (*.md *.markdown *.mdown *.mkd *.mkdn);;"
             "文本文件 (*.txt);;所有文件 (*.*)")
IMAGE_FILTER = "图片 (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.svg);;所有文件 (*.*)"
MAX_RECENT = 12
BASE_PREVIEW_PT = 11
BASE_EDITOR_PT = 11

_windows: list["MainWindow"] = []
_current_theme: Theme | None = None


def current_theme() -> Theme:
    global _current_theme
    if _current_theme is None:
        s = QSettings()
        name = s.value("theme", "")
        if not name:
            try:
                dark = QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
            except Exception:
                dark = False
            name = "dark" if dark else "light"
        _current_theme = THEMES.get(str(name), LIGHT)
    return _current_theme


def set_global_theme(theme: Theme) -> None:
    global _current_theme
    _current_theme = theme
    QSettings().setValue("theme", theme.name)
    apply_app_theme(theme)
    for w in list(_windows):
        w.apply_theme(theme)


def _same_file(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


class MainWindow(QMainWindow):
    def __init__(self, path: str | None = None, initial_text: str | None = None) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        _windows.append(self)
        self.settings = QSettings()
        self.theme = current_theme()
        self.file_path: str | None = None
        self.encoding, self.bom, self.newline = "utf-8", False, "\n"
        self._last_mtime: float | None = None
        self._preview_dirty = True
        self._syncing = False
        self._reload_asking = False
        self._ignore_watch_until = 0.0
        self.zoom = int(self.settings.value("zoom", 0, type=int))
        self.view_mode = str(self.settings.value("viewMode", "split"))

        self.renderer = shared_renderer()
        self.provider = ImageProvider(self)
        self.editor = MarkdownEditor()
        self.editor.image_saver = self._save_pasted_image
        self.editor.link_maker = self._make_link_path
        self.highlighter = MarkdownHighlighter(self.editor.document(), self.theme)
        self.preview = PreviewBrowser(self.provider)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.editor)
        self.splitter.addWidget(self.preview)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(5)
        self.setCentralWidget(self.splitter)

        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(250)
        self.render_timer.timeout.connect(self.render_preview)
        self.stats_timer = QTimer(self)
        self.stats_timer.setSingleShot(True)
        self.stats_timer.setInterval(400)
        self.stats_timer.timeout.connect(self._update_stats)

        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.document().modificationChanged.connect(self._update_title)
        self.editor.cursorPositionChanged.connect(self._update_cursor_status)
        self.editor.filesDropped.connect(self._open_paths)
        self.editor.zoomRequested.connect(self.change_zoom)
        self.preview.zoomRequested.connect(self.change_zoom)
        self.editor.verticalScrollBar().valueChanged.connect(self._editor_scrolled)
        self.preview.verticalScrollBar().valueChanged.connect(self._preview_scrolled)
        self.provider.remoteImageLoaded.connect(self.render_timer.start)
        self.preview.widthChanged.connect(self.render_timer.start)
        self.preview.anchorClicked.connect(self._on_link)
        self.preview.highlighted.connect(lambda url: self.statusBar().showMessage(url.toString(), 4000))

        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._on_file_changed)

        self.find_dialog: FindReplaceDialog | None = None
        self.setAcceptDrops(True)

        self._build_actions()
        self._build_menus()
        self._build_toolbars()
        self._build_statusbar()
        self._restore_settings()
        self.apply_theme(self.theme)

        if path:
            self.load_file(path)
        elif initial_text is not None:
            self.editor.setPlainText(initial_text)
            self.editor.document().setModified(False)
        self._update_title()
        self._update_cursor_status()
        self._update_stats()
        self._update_encoding_status()
        self.render_preview()

    # ================================================================== 动作
    def _act(self, text, slot=None, shortcut=None, tip=None, checkable=False, icon=None,
             checked=False) -> QAction:
        a = QAction(text, self)
        if shortcut:
            if isinstance(shortcut, (list, tuple)):
                a.setShortcuts([QKeySequence(s) for s in shortcut])
            else:
                a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setToolTip(tip)
            a.setStatusTip(tip)
        if checkable:
            a.setCheckable(True)
            a.setChecked(checked)
        if icon is not None:
            a.setIcon(self.style().standardIcon(icon))
        if slot is not None:
            if checkable:
                a.toggled.connect(slot)
            else:
                a.triggered.connect(lambda _=False, f=slot: f())
        return a

    def _build_actions(self) -> None:
        SP = QStyle.StandardPixmap
        K = QKeySequence.StandardKey
        ed = self.editor
        self.a_new = self._act("新建(&N)", self.new_file, K.New, "新建文档", icon=SP.SP_FileIcon)
        self.a_new_window = self._act("新建窗口(&W)", self.new_window, "Ctrl+Shift+N")
        self.a_open = self._act("打开(&O)...", self.open_dialog, K.Open, "打开 Markdown 文件",
                                icon=SP.SP_DialogOpenButton)
        self.a_save = self._act("保存(&S)", self.save, K.Save, "保存", icon=SP.SP_DialogSaveButton)
        self.a_save_as = self._act("另存为(&A)...", self.save_as, "Ctrl+Shift+S")
        self.a_reload = self._act("重新载入(&R)", self.reload_file, None)
        self.a_export_html = self._act("导出为 HTML(&H)...", self.export_html)
        self.a_export_pdf = self._act("导出为 PDF(&D)...", self.export_pdf)
        self.a_print_preview = self._act("打印预览(&V)...", self.print_preview)
        self.a_print = self._act("打印(&P)...", self.print_doc, K.Print)
        self.a_open_folder = self._act("打开所在文件夹", self.open_folder)
        self.a_close = self._act("关闭窗口(&C)", self.close, "Ctrl+W")
        self.a_quit = self._act("退出(&X)", self.quit_all, "Ctrl+Q")

        self.a_undo = self._act("撤销(&U)", ed.undo, K.Undo, "撤销", icon=SP.SP_ArrowBack)
        self.a_redo = self._act("重做(&R)", ed.redo, [QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")],
                                "重做", icon=SP.SP_ArrowForward)
        self.a_undo.setEnabled(False)
        self.a_redo.setEnabled(False)
        ed.undoAvailable.connect(self.a_undo.setEnabled)
        ed.redoAvailable.connect(self.a_redo.setEnabled)
        self.a_cut = self._act("剪切(&T)", ed.cut, K.Cut)
        self.a_copy = self._act("复制(&C)", self._copy, K.Copy)
        self.a_paste = self._act("粘贴(&P)", ed.paste, K.Paste)
        self.a_delete = self._act("删除(&L)", lambda: ed.textCursor().removeSelectedText(), None)
        self.a_select_all = self._act("全选(&A)", self._select_all, K.SelectAll)
        self.a_find = self._act("查找(&F)...", lambda: self.show_find(False), K.Find)
        self.a_find_next = self._act("查找下一个", lambda: self.find_again(True), "F3")
        self.a_find_prev = self._act("查找上一个", lambda: self.find_again(False), "Shift+F3")
        self.a_replace = self._act("替换(&H)...", lambda: self.show_find(True), "Ctrl+H")
        self.a_goto = self._act("转到行(&G)...", self.goto_line, "Ctrl+G")
        self.a_dup = self._act("复制当前行", ed.duplicate_line, "Ctrl+D")
        self.a_del_line = self._act("删除当前行", ed.delete_line, "Ctrl+Shift+K")
        self.a_move_up = self._act("上移行", lambda: ed.move_lines(-1), "Alt+Up")
        self.a_move_down = self._act("下移行", lambda: ed.move_lines(1), "Alt+Down")
        self.a_indent = self._act("增加缩进", ed.indent_lines, None)
        self.a_outdent = self._act("减少缩进", ed.outdent_lines, None)
        self.a_datetime = self._act("插入日期时间", self.insert_datetime, "F5")
        self.a_upper = self._act("转为大写", lambda: self._convert_case(str.upper), "Ctrl+Shift+U")
        self.a_lower = self._act("转为小写", lambda: self._convert_case(str.lower), "Ctrl+U")

        self.a_bold = self._act("粗体", lambda: self.wrap_selection("**", "**", "粗体文字"), K.Bold, "粗体 (Ctrl+B)")
        self.a_italic = self._act("斜体", lambda: self.wrap_selection("*", "*", "斜体文字"), K.Italic, "斜体 (Ctrl+I)")
        self.a_strike = self._act("删除线", lambda: self.wrap_selection("~~", "~~", "删除线文字"), "Alt+Shift+5", "删除线")
        self.a_code = self._act("行内代码", lambda: self.wrap_selection("`", "`", "code"), "Ctrl+`", "行内代码")
        self.a_code_block = self._act("代码块", self.insert_code_block, "Ctrl+Alt+C", "代码块")
        self.a_headings = []
        for lvl in range(1, 7):
            self.a_headings.append(self._act(f"标题 {lvl}", lambda l=lvl: self.set_heading(l),
                                             f"Ctrl+{lvl}", f"{lvl} 级标题"))
        self.a_paragraph = self._act("正文 (取消标题)", lambda: self.set_heading(0))
        self.a_quote = self._act("引用", lambda: self.toggle_prefix("> "), "Ctrl+Shift+Q", "引用")
        self.a_ul = self._act("无序列表", lambda: self.toggle_prefix("- "), "Ctrl+Shift+]", "无序列表")
        self.a_ol = self._act("有序列表", lambda: self.toggle_prefix("1. ", numbered=True), "Ctrl+Shift+[", "有序列表")
        self.a_task = self._act("任务列表", lambda: self.toggle_prefix("- [ ] "), "Ctrl+Shift+X", "任务列表")
        self.a_link = self._act("链接...", self.insert_link, "Ctrl+K", "插入链接")
        self.a_image = self._act("图片...", self.insert_image, "Ctrl+Shift+I", "插入图片")
        self.a_table = self._act("表格...", self.insert_table, "Ctrl+T", "插入表格")
        self.a_hr = self._act("分割线", lambda: self.insert_block("---"), "Ctrl+Shift+-", "分割线")
        self.a_fmt_table = self._act("格式化表格", self.format_tables, "Ctrl+Alt+T",
                                     "对齐光标所在的表格 (不在表格内时格式化全部表格)")

        self.a_view_edit = self._act("仅编辑", lambda: self.set_view_mode("edit"), "Ctrl+Alt+1", "只显示编辑区")
        self.a_view_split = self._act("分屏", lambda: self.set_view_mode("split"), "Ctrl+Alt+2", "编辑 + 预览")
        self.a_view_preview = self._act("仅预览", lambda: self.set_view_mode("preview"), "Ctrl+Alt+3", "只显示预览 (阅读模式)")
        self.view_group = QActionGroup(self)
        for a in (self.a_view_edit, self.a_view_split, self.a_view_preview):
            a.setCheckable(True)
            self.view_group.addAction(a)
        self.a_wrap = self._act("自动换行", self._set_wrap, checkable=True, checked=True)
        self.a_line_numbers = self._act("显示行号", self.editor.set_line_numbers, checkable=True, checked=True)
        self.a_sync = self._act("同步滚动", None, checkable=True, checked=True)
        self.a_dark = self._act("深色主题", lambda on: set_global_theme(DARK if on else LIGHT),
                                "Ctrl+Shift+D", checkable=True)
        self.a_zoom_in = self._act("放大", lambda: self.change_zoom(1), [QKeySequence("Ctrl+="), QKeySequence("Ctrl++")])
        self.a_zoom_out = self._act("缩小", lambda: self.change_zoom(-1), "Ctrl+-")
        self.a_zoom_reset = self._act("重置缩放", lambda: self.change_zoom(0, reset=True), "Ctrl+0")
        self.a_font = self._act("编辑器字体...", self.choose_font)
        self.a_fullscreen = self._act("全屏", self.toggle_fullscreen, "F11", checkable=False)
        self.a_refresh = self._act("刷新预览", self.refresh_preview, "Ctrl+R")

        self.a_help_md = self._act("Markdown 语法示例", self.show_markdown_help, "F1")
        self.a_about = self._act("关于 MDReader", self.show_about)

        self.enc_group = QActionGroup(self)
        self.a_encodings = {}
        for key, label in ((("utf-8", False), "UTF-8"), (("utf-8", True), "UTF-8 带 BOM"),
                           (("gb18030", False), "GBK / GB18030"), (("utf-16", True), "UTF-16 LE")):
            a = self._act(label, lambda k=key: self._set_encoding(*k), checkable=False)
            a.setCheckable(True)
            self.enc_group.addAction(a)
            self.a_encodings[key] = a
        self.eol_group = QActionGroup(self)
        self.a_crlf = self._act("Windows (CRLF)", lambda: self._set_newline("\r\n"))
        self.a_lf = self._act("Unix (LF)", lambda: self._set_newline("\n"))
        for a in (self.a_crlf, self.a_lf):
            a.setCheckable(True)
            self.eol_group.addAction(a)
        self.reopen_actions = []
        for enc, label in (("utf-8", "UTF-8"), ("gb18030", "GBK / GB18030"), ("utf-16", "UTF-16")):
            self.reopen_actions.append(self._act(label, lambda e=enc: self.reload_file(force_encoding=e)))

        # 让快捷键在只显示预览时也生效
        for a in self.findChildren(QAction):
            a.setShortcutContext(Qt.ShortcutContext.WindowShortcut)

    def _build_menus(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu("文件(&F)")
        m.addActions([self.a_new, self.a_new_window, self.a_open])
        self.recent_menu = m.addMenu("最近打开的文件")
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        m.addSeparator()
        m.addActions([self.a_save, self.a_save_as, self.a_reload])
        enc_menu = m.addMenu("保存编码")
        enc_menu.addActions(list(self.a_encodings.values()))
        reopen = m.addMenu("以指定编码重新打开")
        reopen.addActions(self.reopen_actions)
        eol_menu = m.addMenu("换行符")
        eol_menu.addActions([self.a_crlf, self.a_lf])
        m.addSeparator()
        m.addActions([self.a_export_html, self.a_export_pdf, self.a_print_preview, self.a_print])
        m.addSeparator()
        m.addActions([self.a_open_folder, self.a_close, self.a_quit])

        m = mb.addMenu("编辑(&E)")
        m.addActions([self.a_undo, self.a_redo])
        m.addSeparator()
        m.addActions([self.a_cut, self.a_copy, self.a_paste, self.a_delete, self.a_select_all])
        m.addSeparator()
        m.addActions([self.a_find, self.a_find_next, self.a_find_prev, self.a_replace, self.a_goto])
        m.addSeparator()
        lines = m.addMenu("行操作")
        lines.addActions([self.a_dup, self.a_del_line, self.a_move_up, self.a_move_down,
                          self.a_indent, self.a_outdent])
        m.addActions([self.a_upper, self.a_lower, self.a_datetime])

        m = mb.addMenu("格式(&O)")
        m.addActions([self.a_bold, self.a_italic, self.a_strike, self.a_code])
        m.addSeparator()
        hm = m.addMenu("标题")
        hm.addActions(self.a_headings)
        hm.addSeparator()
        hm.addAction(self.a_paragraph)
        m.addActions([self.a_quote, self.a_ul, self.a_ol, self.a_task, self.a_code_block])
        m.addSeparator()
        m.addActions([self.a_link, self.a_image, self.a_table, self.a_hr])
        m.addSeparator()
        m.addAction(self.a_fmt_table)

        m = mb.addMenu("视图(&V)")
        m.addActions([self.a_view_edit, self.a_view_split, self.a_view_preview])
        m.addSeparator()
        m.addActions([self.a_wrap, self.a_line_numbers, self.a_sync, self.a_dark])
        m.addSeparator()
        m.addActions([self.a_zoom_in, self.a_zoom_out, self.a_zoom_reset, self.a_font])
        m.addSeparator()
        self.toolbar_menu = m.addMenu("工具栏")
        m.addActions([self.a_refresh, self.a_fullscreen])

        m = mb.addMenu("帮助(&H)")
        m.addActions([self.a_help_md, self.a_about])

    def _build_toolbars(self) -> None:
        tb = QToolBar("文件", self)
        tb.setObjectName("fileToolbar")
        tb.setIconSize(QSize(18, 18))
        tb.addActions([self.a_new, self.a_open, self.a_save])
        tb.addSeparator()
        tb.addActions([self.a_undo, self.a_redo])
        self.addToolBar(tb)

        ft = QToolBar("格式", self)
        ft.setObjectName("formatToolbar")
        ft.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        labels = [(self.a_bold, "B"), (self.a_italic, "I"), (self.a_strike, "S"),
                  (self.a_headings[0], "H1"), (self.a_headings[1], "H2"), (self.a_headings[2], "H3"),
                  None, (self.a_quote, "引用"), (self.a_ul, "• 列表"), (self.a_ol, "1. 列表"),
                  (self.a_task, "☑ 任务"), (self.a_code, "</>"), (self.a_code_block, "代码块"),
                  None, (self.a_link, "链接"), (self.a_image, "图片"), (self.a_table, "表格"),
                  (self.a_hr, "—"), (self.a_fmt_table, "对齐表格")]
        for item in labels:
            if item is None:
                ft.addSeparator()
                continue
            action, label = item
            proxy = QAction(label, self)
            proxy.setToolTip(action.toolTip() + (f"  ({action.shortcut().toString()})"
                                                 if not action.shortcut().isEmpty() else ""))
            proxy.triggered.connect(action.trigger)
            if label in ("B", "I", "S"):
                f = QFont()
                f.setBold(label == "B")
                f.setItalic(label == "I")
                f.setStrikeOut(label == "S")
                proxy.setFont(f)
            ft.addAction(proxy)
        self.addToolBar(ft)

        vt = QToolBar("视图", self)
        vt.setObjectName("viewToolbar")
        vt.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        vt.addActions([self.a_view_edit, self.a_view_split, self.a_view_preview])
        self.addToolBar(vt)
        for t in (tb, ft, vt):
            self.toolbar_menu.addAction(t.toggleViewAction())

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        self.lbl_pos = QLabel()
        self.lbl_stats = QLabel()
        self.lbl_eol = QLabel()
        self.lbl_enc = QLabel()
        self.lbl_zoom = QLabel()
        for w in (self.lbl_pos, self.lbl_stats, self.lbl_zoom, self.lbl_eol, self.lbl_enc):
            w.setContentsMargins(8, 0, 8, 0)
            sb.addPermanentWidget(w)

    # ================================================================== 设置
    def _restore_settings(self) -> None:
        s = self.settings
        geo = s.value("geometry")
        if geo is not None and not _windows[:-1]:
            self.restoreGeometry(geo)
        else:
            self.resize(1280, 800)
            if len(_windows) > 1:
                prev = _windows[-2]
                self.move(prev.pos().x() + 30, prev.pos().y() + 30)
                self.resize(prev.size())
        state = s.value("windowState")
        if state is not None:
            self.restoreState(state)
        sp = s.value("splitter")
        if sp is not None:
            self.splitter.restoreState(sp)
        else:
            self.splitter.setSizes([1, 1])
        self.a_wrap.setChecked(s.value("wordWrap", True, type=bool))
        self._set_wrap(self.a_wrap.isChecked())
        self.a_line_numbers.setChecked(s.value("lineNumbers", True, type=bool))
        self.a_sync.setChecked(s.value("syncScroll", True, type=bool))
        self.a_dark.blockSignals(True)
        self.a_dark.setChecked(self.theme.dark)
        self.a_dark.blockSignals(False)
        self._apply_fonts()
        self.set_view_mode(self.view_mode, render=False)

    def _save_settings(self) -> None:
        s = self.settings
        s.setValue("geometry", self.saveGeometry())
        s.setValue("windowState", self.saveState())
        s.setValue("splitter", self.splitter.saveState())
        s.setValue("viewMode", self.view_mode)
        s.setValue("wordWrap", self.a_wrap.isChecked())
        s.setValue("lineNumbers", self.a_line_numbers.isChecked())
        s.setValue("syncScroll", self.a_sync.isChecked())
        s.setValue("zoom", self.zoom)

    def _editor_base_font(self) -> QFont:
        fam = self.settings.value("editorFont", "")
        size = int(self.settings.value("editorFontSize", BASE_EDITOR_PT, type=int))
        f = QFont()
        if fam:
            f.setFamilies([str(fam), "Microsoft YaHei UI"])
        else:
            f.setFamilies(["Consolas", "Microsoft YaHei UI", "Courier New"])
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setPointSize(size)
        return f

    def _apply_fonts(self) -> None:
        f = self._editor_base_font()
        f.setPointSize(max(6, f.pointSize() + self.zoom))
        self.editor.set_editor_font(f)
        self.lbl_zoom.setText(f"缩放 {100 + self.zoom * 10}%")

    # ================================================================== 主题 / 视图
    def apply_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.editor.set_theme(theme)
        self.highlighter.set_theme(theme)
        self.preview.setStyleSheet(
            f"QTextBrowser {{ background-color:{theme.background}; color:{theme.text}; border:none;"
            f" selection-background-color:{theme.ed_selection}; selection-color:{theme.ed_selection_text}; }}")
        self.a_dark.blockSignals(True)
        self.a_dark.setChecked(theme.dark)
        self.a_dark.blockSignals(False)
        self.render_preview()

    def set_view_mode(self, mode: str, render: bool = True) -> None:
        if mode not in ("edit", "split", "preview"):
            mode = "split"
        self.view_mode = mode
        self.editor.setVisible(mode != "preview")
        self.preview.setVisible(mode != "edit")
        {"edit": self.a_view_edit, "split": self.a_view_split,
         "preview": self.a_view_preview}[mode].setChecked(True)
        if mode == "preview":
            self.preview.setFocus()
        else:
            self.editor.setFocus()
        if render and mode != "edit" and self._preview_dirty:
            self.render_preview()

    def _set_wrap(self, on: bool) -> None:
        from PyQt6.QtWidgets import QPlainTextEdit
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if on
                                    else QPlainTextEdit.LineWrapMode.NoWrap)

    def change_zoom(self, delta: int, reset: bool = False) -> None:
        self.zoom = 0 if reset else max(-6, min(20, self.zoom + delta))
        self._apply_fonts()
        self.render_preview()

    def choose_font(self) -> None:
        ok_font, ok = QFontDialog.getFont(self._editor_base_font(), self, "选择编辑器字体")
        if ok:
            self.settings.setValue("editorFont", ok_font.family())
            self.settings.setValue("editorFontSize", ok_font.pointSize())
            for w in _windows:
                w._apply_fonts()

    def toggle_fullscreen(self) -> None:
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    # ================================================================== 预览
    def _base_dir(self) -> str:
        if self.file_path:
            return os.path.dirname(self.file_path)
        return os.getcwd()

    def _on_text_changed(self) -> None:
        self._preview_dirty = True
        self.render_timer.start()
        self.stats_timer.start()

    def render_preview(self) -> None:
        if self.view_mode == "edit":
            self._preview_dirty = True
            return
        self._preview_dirty = False
        self.provider.base_dir = self._base_dir()
        pt = max(6, BASE_PREVIEW_PT + self.zoom)
        html = self.renderer.render_qt(self.editor.toPlainText(), self.theme, pt)
        sb = self.preview.verticalScrollBar()
        old_value = sb.value()
        doc = self.preview.document()
        doc.setDefaultFont(body_font(pt))
        doc.setDefaultStyleSheet(qt_stylesheet(self.theme, pt))
        self._syncing = True
        self.preview.setHtml(html)
        self._syncing = False
        self._restore_preview_scroll(old_value)
        QTimer.singleShot(0, lambda v=old_value: self._restore_preview_scroll(v))

    def _restore_preview_scroll(self, old_value: int) -> None:
        sb = self.preview.verticalScrollBar()
        self._syncing = True
        if self.a_sync.isChecked() and self.view_mode == "split":
            esb = self.editor.verticalScrollBar()
            ratio = esb.value() / esb.maximum() if esb.maximum() > 0 else 0.0
            sb.setValue(round(ratio * sb.maximum()))
        else:
            sb.setValue(old_value)
        self._syncing = False

    def refresh_preview(self) -> None:
        self.provider.clear_cache()
        self.render_preview()

    def _editor_scrolled(self, value: int) -> None:
        if self._syncing or not self.a_sync.isChecked() or self.view_mode != "split":
            return
        esb, psb = self.editor.verticalScrollBar(), self.preview.verticalScrollBar()
        ratio = value / esb.maximum() if esb.maximum() > 0 else 0.0
        self._syncing = True
        psb.setValue(round(ratio * psb.maximum()))
        self._syncing = False

    def _preview_scrolled(self, value: int) -> None:
        if self._syncing or not self.a_sync.isChecked() or self.view_mode != "split":
            return
        esb, psb = self.editor.verticalScrollBar(), self.preview.verticalScrollBar()
        ratio = value / psb.maximum() if psb.maximum() > 0 else 0.0
        self._syncing = True
        esb.setValue(round(ratio * esb.maximum()))
        self._syncing = False

    def _on_link(self, url: QUrl) -> None:
        s = url.toString()
        if s.startswith("#"):
            self.preview.scrollToAnchor(unquote(s[1:]))
            return
        if not WIN_ABS_RE.match(s) and url.scheme().lower() in ("http", "https", "mailto", "ftp"):
            QDesktopServices.openUrl(url)
            return
        path_part, _, anchor = s.partition("#")
        if url.scheme().lower() == "file":
            path = url.toLocalFile()
        else:
            path = unquote(path_part)
            if not WIN_ABS_RE.match(path):
                path = os.path.join(self._base_dir(), path)
        path = os.path.normpath(path)
        if not os.path.exists(path):
            QMessageBox.warning(self, APP_NAME, f"找不到链接目标:\n{path}")
            return
        if os.path.splitext(path)[1].lower() in MD_EXTS:
            w = self.open_path(path)
            if anchor and w is not None:
                QTimer.singleShot(50, lambda: w.preview.scrollToAnchor(unquote(anchor)))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ================================================================== 文件
    def is_pristine(self) -> bool:
        return (self.file_path is None and not self.editor.document().isModified()
                and not self.editor.toPlainText())

    def new_file(self) -> None:
        if not self.maybe_save():
            return
        self._unwatch()
        self.file_path = None
        self.encoding, self.bom, self.newline = "utf-8", False, "\n"
        self.editor.setPlainText("")
        self.editor.document().setModified(False)
        self._update_title()
        self._update_encoding_status()
        self.render_preview()

    def new_window(self, initial_text: str | None = None) -> "MainWindow":
        w = MainWindow(initial_text=initial_text)
        w.show()
        return w

    def open_dialog(self) -> None:
        start = os.path.dirname(self.file_path) if self.file_path else \
            str(self.settings.value("lastDir", os.path.expanduser("~")))
        paths, _ = QFileDialog.getOpenFileNames(self, "打开文件", start, MD_FILTER)
        self._open_paths(paths)

    def _open_paths(self, paths) -> None:
        for p in paths:
            self.open_path(p)

    def open_path(self, path: str) -> "MainWindow | None":
        path = os.path.abspath(path)
        for w in _windows:
            if w.file_path and _same_file(w.file_path, path):
                if w.isMinimized():
                    w.showNormal()
                w.raise_()
                w.activateWindow()
                return w
        if self.is_pristine():
            return self if self.load_file(path) else None
        w = MainWindow(path)
        w.show()
        return w

    def load_file(self, path: str, force_encoding: str | None = None,
                  keep_position: bool = False) -> bool:
        try:
            info = read_text_file(path, force_encoding)
        except OSError as e:
            QMessageBox.critical(self, APP_NAME, f"无法打开文件:\n{path}\n\n{e}")
            self._remove_recent(path)
            return False
        cursor_pos = self.editor.textCursor().position()
        scroll = self.editor.verticalScrollBar().value()
        self._unwatch()
        self.file_path = os.path.abspath(path)
        self.encoding, self.bom, self.newline = info.encoding, info.bom, info.newline
        self.provider.base_dir = os.path.dirname(self.file_path)
        self.editor.setPlainText(info.text)
        self.editor.document().setModified(False)
        if keep_position:
            c = self.editor.textCursor()
            c.setPosition(min(cursor_pos, self.editor.document().characterCount() - 1))
            self.editor.setTextCursor(c)
            self.editor.verticalScrollBar().setValue(scroll)
        self._watch()
        self._add_recent(self.file_path)
        self.settings.setValue("lastDir", os.path.dirname(self.file_path))
        self._update_title()
        self._update_encoding_status()
        self.render_preview()
        return True

    def reload_file(self, force_encoding: str | None = None) -> None:
        if not self.file_path:
            return
        if self.editor.document().isModified():
            r = QMessageBox.question(self, APP_NAME, "放弃未保存的修改并重新载入文件吗?")
            if r != QMessageBox.StandardButton.Yes:
                return
        self.load_file(self.file_path, force_encoding, keep_position=True)

    def save(self) -> bool:
        if not self.file_path:
            return self.save_as()
        return self._write(self.file_path)

    def save_as(self) -> bool:
        if self.file_path:
            start = self.file_path
        else:
            first = self.editor.toPlainText().strip().split("\n", 1)[0].lstrip("#").strip()
            name = re.sub(r'[\\/:*?"<>|]', "", first)[:40] or "未命名"
            start = os.path.join(str(self.settings.value("lastDir", os.path.expanduser("~"))), name + ".md")
        path, _ = QFileDialog.getSaveFileName(self, "另存为", start, MD_FILTER)
        if not path:
            return False
        if not os.path.splitext(path)[1]:
            path += ".md"
        old_dir = self._base_dir()
        ok = self._write(path)
        if ok:
            self._unwatch()
            self.file_path = os.path.abspath(path)
            self._watch()
            self._add_recent(self.file_path)
            self.settings.setValue("lastDir", os.path.dirname(self.file_path))
            self._update_title()
            if not _same_file(old_dir, self._base_dir()):
                self.render_preview()
        return ok

    def _write(self, path: str) -> bool:
        info = TextFileInfo(self.editor.toPlainText(), self.encoding, self.bom, self.newline)
        watched = self.file_path and _same_file(path, self.file_path)
        if watched:
            self._unwatch()
        try:
            write_text_file(path, info)
        except (OSError, UnicodeError) as e:
            QMessageBox.critical(self, APP_NAME, f"保存失败:\n{path}\n\n{e}")
            if watched:
                self._watch()
            return False
        if watched:
            self._watch()
        self.editor.document().setModified(False)
        self.statusBar().showMessage(f"已保存: {path}", 3000)
        return True

    def maybe_save(self) -> bool:
        if not self.editor.document().isModified():
            return True
        name = os.path.basename(self.file_path) if self.file_path else "未命名"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(APP_NAME)
        box.setText(f"“{name}” 有未保存的修改。")
        box.setInformativeText("是否保存修改?")
        b_save = box.addButton("保存", QMessageBox.ButtonRole.AcceptRole)
        b_discard = box.addButton("不保存", QMessageBox.ButtonRole.DestructiveRole)
        b_cancel = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(b_save)
        box.exec()
        clicked = box.clickedButton()
        if clicked == b_save:
            return self.save()
        return clicked == b_discard

    # ---- 文件监视
    def _watch(self) -> None:
        if self.file_path and os.path.exists(self.file_path):
            self.watcher.addPath(self.file_path)
            self._last_mtime = os.path.getmtime(self.file_path)

    def _unwatch(self) -> None:
        files = self.watcher.files()
        if files:
            self.watcher.removePaths(files)

    def _on_file_changed(self, path: str) -> None:
        QTimer.singleShot(200, lambda: self._check_external_change(path))

    def _check_external_change(self, path: str) -> None:
        if not self.file_path or not _same_file(path, self.file_path) or self._reload_asking:
            return
        if not os.path.exists(path):
            self.statusBar().showMessage("文件已在磁盘上被删除或重命名", 8000)
            self.editor.document().setModified(True)
            return
        if path not in self.watcher.files():
            self.watcher.addPath(path)
        mtime = os.path.getmtime(path)
        if self._last_mtime is not None and abs(mtime - self._last_mtime) < 1e-6:
            return
        self._last_mtime = mtime
        if not self.editor.document().isModified():
            self.load_file(path, keep_position=True)
            self.statusBar().showMessage("文件已被外部程序修改, 已自动重新载入", 5000)
            return
        self._reload_asking = True
        try:
            r = QMessageBox.question(
                self, APP_NAME,
                f"文件已被其他程序修改:\n{path}\n\n是否重新载入? (将丢失当前未保存的修改)")
            if r == QMessageBox.StandardButton.Yes:
                self.load_file(path, keep_position=True)
        finally:
            self._reload_asking = False

    # ---- 最近文件
    def _recent(self) -> list[str]:
        v = self.settings.value("recentFiles", [], type=list)
        return [str(x) for x in v if x]

    def _add_recent(self, path: str) -> None:
        lst = [p for p in self._recent() if not _same_file(p, path)]
        lst.insert(0, path)
        self.settings.setValue("recentFiles", lst[:MAX_RECENT])

    def _remove_recent(self, path: str) -> None:
        self.settings.setValue("recentFiles", [p for p in self._recent() if not _same_file(p, path)])

    def _fill_recent_menu(self) -> None:
        self.recent_menu.clear()
        files = self._recent()
        if not files:
            a = self.recent_menu.addAction("(无)")
            a.setEnabled(False)
            return
        for i, p in enumerate(files):
            a = self.recent_menu.addAction(f"&{(i + 1) % 10}  {p}" if i < 10 else p)
            a.triggered.connect(lambda _=False, path=p: self.open_path(path))
        self.recent_menu.addSeparator()
        self.recent_menu.addAction("清除列表").triggered.connect(
            lambda: self.settings.setValue("recentFiles", []))

    def open_folder(self) -> None:
        if self.file_path:
            import subprocess
            subprocess.Popen(["explorer", "/select,", os.path.normpath(self.file_path)])

    # ---- 编码 / 换行
    def _set_encoding(self, enc: str, bom: bool) -> None:
        if (enc, bom) != (self.encoding, self.bom):
            self.encoding, self.bom = enc, bom
            self.editor.document().setModified(True)
        self._update_encoding_status()

    def _set_newline(self, nl: str) -> None:
        if nl != self.newline:
            self.newline = nl
            self.editor.document().setModified(True)
        self._update_encoding_status()

    def _update_encoding_status(self) -> None:
        self.lbl_enc.setText(encoding_label(self.encoding, self.bom))
        self.lbl_eol.setText("CRLF" if self.newline == "\r\n" else "LF")
        a = self.a_encodings.get((self.encoding, self.bom))
        if a:
            a.setChecked(True)
        (self.a_crlf if self.newline == "\r\n" else self.a_lf).setChecked(True)

    # ================================================================== 导出 / 打印
    def _title(self) -> str:
        if self.file_path:
            return os.path.splitext(os.path.basename(self.file_path))[0]
        return "未命名"

    def _default_export_path(self, ext: str) -> str:
        if self.file_path:
            return os.path.splitext(self.file_path)[0] + ext
        return os.path.join(str(self.settings.value("lastDir", os.path.expanduser("~"))), "未命名" + ext)

    def export_html(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出 HTML", self._default_export_path(".html"),
                                              "HTML 文件 (*.html *.htm)")
        if not path:
            return
        r = QMessageBox.question(
            self, "导出 HTML",
            "是否把本地图片嵌入到 HTML 文件中?\n\n"
            "是: 生成单个独立文件, 可直接发送给他人\n否: 以相对路径引用图片",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        embed = r == QMessageBox.StandardButton.Yes
        out_dir = os.path.dirname(os.path.abspath(path))
        self.provider.base_dir = self._base_dir()

        def rewrite(src: str) -> str:
            local = self.provider.local_path(src)
            if local is None or not os.path.isfile(local):
                return src
            if embed:
                mime = mimetypes.guess_type(local)[0] or "application/octet-stream"
                if local.lower().endswith(".svg"):
                    mime = "image/svg+xml"
                with open(local, "rb") as f:
                    return f"data:{mime};base64," + base64.b64encode(f.read()).decode("ascii")
            try:
                rel = os.path.relpath(local, out_dir)
            except ValueError:
                return QUrl.fromLocalFile(local).toString()
            return quote(rel.replace("\\", "/"), safe="/._-~()")

        html = self.renderer.export_html(self.editor.toPlainText(), self._title(), rewrite)
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(html)
        except OSError as e:
            QMessageBox.critical(self, APP_NAME, f"导出失败:\n{e}")
            return
        self.statusBar().showMessage(f"已导出 HTML: {path}", 5000)
        r = QMessageBox.question(self, "导出 HTML", f"已导出:\n{path}\n\n是否在浏览器中打开?")
        if r == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _build_print_document(self, printer: QPrinter) -> RenderDocument:
        self.provider.base_dir = self._base_dir()
        page = printer.pageLayout().paintRectPixels(printer.resolution())
        width_px = page.width() * 96 / printer.resolution()
        doc = RenderDocument(self.provider, int(width_px - 10), self)
        pt = BASE_PREVIEW_PT
        doc.setDefaultFont(body_font(pt))
        doc.setDefaultStyleSheet(qt_stylesheet(LIGHT, pt))
        doc.setDocumentMargin(0)
        doc.setHtml(self.renderer.render_qt(self.editor.toPlainText(), LIGHT, pt))
        doc.prepare(int(width_px))
        return doc

    def _make_printer(self, pdf_path: str | None = None) -> QPrinter:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setPageMargins(QMarginsF(16, 16, 16, 16), QPageLayout.Unit.Millimeter)
        printer.setDocName(self._title())
        if pdf_path:
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(pdf_path)
        return printer

    def export_pdf(self, path: str | None = None, ask_open: bool = True) -> bool:
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "导出 PDF", self._default_export_path(".pdf"),
                                                  "PDF 文件 (*.pdf)")
            if not path:
                return False
        printer = self._make_printer(path)
        doc = self._build_print_document(printer)
        doc.print(printer)
        self.statusBar().showMessage(f"已导出 PDF: {path}", 5000)
        if ask_open:
            r = QMessageBox.question(self, "导出 PDF", f"已导出:\n{path}\n\n是否立即打开?")
            if r == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        return True

    def print_doc(self) -> None:
        printer = self._make_printer()
        dlg = QPrintDialog(printer, self)
        dlg.setWindowTitle("打印")
        if dlg.exec() == QPrintDialog.DialogCode.Accepted:
            self._build_print_document(printer).print(printer)

    def print_preview(self) -> None:
        printer = self._make_printer()
        dlg = QPrintPreviewDialog(printer, self)
        dlg.setWindowTitle("打印预览")
        dlg.resize(1000, 800)
        dlg.paintRequested.connect(lambda p: self._build_print_document(p).print(p))
        dlg.exec()

    # ================================================================== 编辑操作
    def _copy(self) -> None:
        if self.preview.hasFocus():
            self.preview.copy()
        else:
            self.editor.copy()

    def _select_all(self) -> None:
        if self.preview.hasFocus():
            self.preview.selectAll()
        else:
            self.editor.selectAll()

    def show_find(self, replace: bool) -> None:
        if self.find_dialog is None:
            self.find_dialog = FindReplaceDialog(self, lambda: self.editor)
        if self.view_mode == "preview":
            self.set_view_mode("split")
        self.find_dialog.show_find(replace)

    def find_again(self, forward: bool) -> None:
        if self.find_dialog is None or not self.find_dialog.has_pattern():
            self.show_find(False)
            return
        self.find_dialog.find(forward)

    def goto_line(self) -> None:
        n = self.editor.blockCount()
        cur = self.editor.textCursor().blockNumber() + 1
        line, ok = QInputDialog.getInt(self, "转到行", f"行号 (1 - {n}):", cur, 1, n)
        if ok:
            block = self.editor.document().findBlockByNumber(line - 1)
            c = self.editor.textCursor()
            c.setPosition(block.position())
            self.editor.setTextCursor(c)
            self.editor.centerCursor()
            self.editor.setFocus()

    def insert_datetime(self) -> None:
        self.editor.textCursor().insertText(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))

    def _convert_case(self, func) -> None:
        c = self.editor.textCursor()
        if not c.hasSelection():
            return
        start, end = c.selectionStart(), c.selectionEnd()
        text = c.selectedText().replace(" ", "\n")
        c.insertText(func(text))
        c.setPosition(start)
        c.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(c)

    def _ensure_editor_visible(self) -> None:
        if self.view_mode == "preview":
            self.set_view_mode("split")
        self.editor.setFocus()

    def wrap_selection(self, prefix: str, suffix: str, placeholder: str) -> None:
        self._ensure_editor_visible()
        c = self.editor.textCursor()
        doc = self.editor.document()
        if c.hasSelection():
            start, end = c.selectionStart(), c.selectionEnd()
            text = c.selectedText()
            lp, ls = u16len(prefix), u16len(suffix)
            # 已被包裹 -> 取消
            if text.startswith(prefix) and text.endswith(suffix) and len(text) >= len(prefix) + len(suffix):
                inner = text[len(prefix):len(text) - len(suffix)]
                c.insertText(inner.replace(" ", "\n"))
                c.setPosition(start)
                c.setPosition(start + u16len(inner), QTextCursor.MoveMode.KeepAnchor)
                self.editor.setTextCursor(c)
                return
            chk = QTextCursor(doc)
            if start >= lp and end + ls <= doc.characterCount() - 1:
                chk.setPosition(start - lp)
                chk.setPosition(end + ls, QTextCursor.MoveMode.KeepAnchor)
                around = chk.selectedText()
                if around.startswith(prefix) and around.endswith(suffix):
                    c.beginEditBlock()
                    c2 = QTextCursor(doc)
                    c2.setPosition(end)
                    c2.setPosition(end + ls, QTextCursor.MoveMode.KeepAnchor)
                    c2.removeSelectedText()
                    c2.setPosition(start - lp)
                    c2.setPosition(start, QTextCursor.MoveMode.KeepAnchor)
                    c2.removeSelectedText()
                    c.endEditBlock()
                    c.setPosition(start - lp)
                    c.setPosition(end - lp, QTextCursor.MoveMode.KeepAnchor)
                    self.editor.setTextCursor(c)
                    return
            c.beginEditBlock()
            c.insertText(prefix + text.replace(" ", "\n") + suffix)
            c.endEditBlock()
            c.setPosition(start + lp)
            c.setPosition(end + lp, QTextCursor.MoveMode.KeepAnchor)
        else:
            pos = c.position()
            c.insertText(prefix + placeholder + suffix)
            c.setPosition(pos + u16len(prefix))
            c.setPosition(pos + u16len(prefix + placeholder), QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(c)

    def set_heading(self, level: int) -> None:
        self._ensure_editor_visible()

        def f(lines):
            out = []
            for l in lines:
                m = re.match(r"^(\s{0,3})(#{1,6})\s+", l)
                body = l[m.end():] if m else l.lstrip()
                cur_level = len(m.group(2)) if m else 0
                if level == 0 or cur_level == level:
                    out.append(body)
                else:
                    out.append("#" * level + " " + body)
            return out
        self.editor.transform_lines(f, select=False)

    def toggle_prefix(self, prefix: str, numbered: bool = False) -> None:
        self._ensure_editor_visible()
        list_re = re.compile(r"^(\s*)(?:[-*+]\s+\[[ xX]\]\s+|[-*+]\s+|\d+[.)]\s+)")

        def f(lines):
            non_empty = [l for l in lines if l.strip()] or lines
            if numbered:
                has = all(re.match(r"^\s*\d+[.)]\s+", l) for l in non_empty)
            elif prefix == "> ":
                has = all(l.lstrip().startswith(">") for l in non_empty)
            elif prefix == "- [ ] ":
                has = all(re.match(r"^\s*[-*+]\s+\[[ xX]\]\s", l) for l in non_empty)
            else:
                has = all(re.match(r"^\s*[-*+]\s+(?!\[[ xX]\])", l) for l in non_empty)
            out, n = [], 0
            for l in lines:
                if not l.strip() and len(lines) > 1:
                    out.append(l)
                    continue
                if prefix == "> ":
                    out.append(re.sub(r"^(\s*)>\s?", r"\1", l, count=1) if has else "> " + l)
                    continue
                m = list_re.match(l)
                indent = m.group(1) if m else re.match(r"^\s*", l).group(0)
                body = l[m.end():] if m else l.lstrip()
                if has:
                    out.append(indent + body)
                else:
                    n += 1
                    out.append(indent + (f"{n}. " if numbered else prefix) + body)
            return out
        self.editor.transform_lines(f, select=False)

    def insert_block(self, text: str, select_from: int | None = None, select_len: int = 0) -> None:
        """在当前位置插入块级内容, 自动补充前后空行。"""
        self._ensure_editor_visible()
        c = self.editor.textCursor()
        c.clearSelection()
        block_text = c.block().text()
        before = ""
        if block_text.strip():
            c.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            before = "\n\n"
        else:
            prev = c.block().previous()
            if prev.isValid() and prev.text().strip():
                before = "\n"
        nxt = c.block().next()
        after = "\n\n" if nxt.isValid() and nxt.text().strip() else "\n"
        start = c.position()
        c.insertText(before + text + after)
        base = start + u16len(before)
        if select_from is not None:
            c.setPosition(base + select_from)
            c.setPosition(base + select_from + select_len, QTextCursor.MoveMode.KeepAnchor)
        else:
            c.setPosition(base + u16len(text) + u16len(after))
        self.editor.setTextCursor(c)

    def insert_code_block(self) -> None:
        c = self.editor.textCursor()
        if c.hasSelection():
            text = c.selectedText().replace(" ", "\n")
            c.insertText("```\n" + text + "\n```")
            c.setPosition(c.position() - u16len(text) - 8 + 3)
            self.editor.setTextCursor(c)
            return
        self.insert_block("```\n\n```", select_from=3, select_len=0)

    def insert_link(self) -> None:
        self._ensure_editor_visible()
        c = self.editor.textCursor()
        sel = c.selectedText() if c.hasSelection() else ""
        url = ""
        clip = QApplication.clipboard().text().strip()
        if re.match(r"^https?://\S+$", clip):
            url = clip
        dlg = LinkDialog(self, sel, url)
        if dlg.exec():
            c.insertText(dlg.markdown())

    def insert_image(self) -> None:
        self._ensure_editor_visible()
        start = self._base_dir()
        paths, _ = QFileDialog.getOpenFileNames(self, "插入图片", start, IMAGE_FILTER)
        if not paths:
            return
        parts = []
        for p in paths:
            name = os.path.splitext(os.path.basename(p))[0]
            parts.append(f"![{name}]({self._make_link_path(p)})")
        self.editor.textCursor().insertText("\n".join(parts))

    def insert_table(self) -> None:
        dlg = InsertTableDialog(self)
        if dlg.exec():
            text = make_table(dlg.rows.value(), dlg.cols.value(), dlg.align.currentData())
            self.insert_block(text, select_from=2, select_len=u16len("列1"))

    def format_tables(self) -> None:
        self._ensure_editor_visible()
        text = self.editor.toPlainText()
        lines = text.split("\n")
        line_no = self.editor.textCursor().blockNumber()
        for start, end in find_tables(lines):
            if start <= line_no < end:
                new = format_table(lines[start:end])
                if new:
                    doc = self.editor.document()
                    c = QTextCursor(doc)
                    c.beginEditBlock()
                    c.setPosition(doc.findBlockByNumber(start).position())
                    last = doc.findBlockByNumber(end - 1)
                    c.setPosition(last.position() + last.length() - 1, QTextCursor.MoveMode.KeepAnchor)
                    c.insertText("\n".join(new))
                    c.endEditBlock()
                    self.statusBar().showMessage("表格已对齐", 3000)
                return
        new_text, n = format_all_tables(text)
        if n and new_text != text:
            vs = self.editor.verticalScrollBar().value()
            pos = self.editor.textCursor().position()
            c = QTextCursor(self.editor.document())
            c.beginEditBlock()
            c.select(QTextCursor.SelectionType.Document)
            c.insertText(new_text)
            c.endEditBlock()
            c.setPosition(min(pos, self.editor.document().characterCount() - 1))
            self.editor.setTextCursor(c)
            self.editor.verticalScrollBar().setValue(vs)
        self.statusBar().showMessage(f"已格式化 {n} 个表格" if n else "文档中没有表格", 3000)

    # ---- 图片路径 / 粘贴图片
    def _make_link_path(self, path: str) -> str:
        path = os.path.abspath(path)
        if self.file_path:
            try:
                rel = os.path.relpath(path, os.path.dirname(self.file_path))
                path = rel
            except ValueError:
                pass
        p = path.replace("\\", "/")
        if any(ch in p for ch in " ()<>"):
            p = f"<{p}>"
        return p

    def _save_pasted_image(self, img) -> str | None:
        if not self.file_path:
            r = QMessageBox.question(self, "粘贴图片",
                                     "粘贴的图片需要保存到文档所在目录的 images 文件夹中。\n"
                                     "当前文档尚未保存, 是否现在保存?")
            if r != QMessageBox.StandardButton.Yes or not self.save_as():
                return None
        folder = os.path.join(os.path.dirname(self.file_path), "images")
        os.makedirs(folder, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        name, i = f"image-{stamp}.png", 1
        while os.path.exists(os.path.join(folder, name)):
            name = f"image-{stamp}-{i}.png"
            i += 1
        full = os.path.join(folder, name)
        if not img.save(full, "PNG"):
            QMessageBox.critical(self, APP_NAME, f"保存图片失败:\n{full}")
            return None
        self.statusBar().showMessage(f"图片已保存: {full}", 4000)
        return f"![image]({self._make_link_path(full)})"

    # ================================================================== 状态
    def _update_title(self, *_):
        name = os.path.basename(self.file_path) if self.file_path else "未命名"
        self.setWindowTitle(f"{name}[*] - {APP_NAME}")
        self.setWindowModified(self.editor.document().isModified())
        self.a_reload.setEnabled(bool(self.file_path))
        self.a_open_folder.setEnabled(bool(self.file_path))

    def _update_cursor_status(self) -> None:
        c = self.editor.textCursor()
        line = c.blockNumber() + 1
        col = c.positionInBlock() + 1
        sel = ""
        if c.hasSelection():
            sel = f"  (已选 {len(c.selectedText())} 字符)"
        self.lbl_pos.setText(f"行 {line}, 列 {col}{sel}")

    def _update_stats(self) -> None:
        text = self.editor.toPlainText()
        cjk = len(re.findall(r"[㐀-䶿一-鿿豈-﫿぀-ヿ가-힯]", text))
        words = len(re.findall(r"[A-Za-z0-9_][A-Za-z0-9_'\-.]*", text))
        chars = len(text)
        self.lbl_stats.setText(f"字数 {cjk + words}  |  字符 {chars}  |  {self.editor.blockCount()} 行")

    # ================================================================== 帮助
    def show_markdown_help(self) -> None:
        img_path = os.path.join(tempfile.gettempdir(), "mdreader-help", "sample.png")
        try:
            os.makedirs(os.path.dirname(img_path), exist_ok=True)
            if not os.path.exists(img_path):
                from .icon import make_icon_image
                make_icon_image(160).save(img_path, "PNG")
        except OSError:
            pass
        self.new_window(help_markdown(img_path.replace("\\", "/")))

    def show_about(self) -> None:
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
        QMessageBox.about(
            self, "关于 MDReader",
            f"<h3>{APP_TITLE} {__version__}</h3>"
            "<p>读取、编辑并实时预览 Markdown 文件。支持表格、图片、代码高亮、任务列表、脚注,"
            "可导出 HTML / PDF 及打印。</p>"
            f"<p>Qt {QT_VERSION_STR} · PyQt {PYQT_VERSION_STR} · markdown-it-py · Pygments</p>")

    def quit_all(self) -> None:
        for w in list(_windows):
            if not w.close():
                return

    # ================================================================== 事件
    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        md = [p for p in paths if os.path.splitext(p)[1].lower() in MD_EXTS]
        self._open_paths(md)

    def closeEvent(self, e) -> None:
        if not self.maybe_save():
            e.ignore()
            return
        self._save_settings()
        if self.find_dialog:
            self.find_dialog.close()
        if self in _windows:
            _windows.remove(self)
        e.accept()


def help_markdown(image_path: str) -> str:
    return f"""# Markdown 语法示例

> 这是一个未命名的新文档, 左边是源码, 右边是实时预览。可以随意修改试试看。

## 1. 文字格式

**粗体**、*斜体*、~~删除线~~、`行内代码`、***粗斜体***

## 2. 标题

使用 1~6 个 `#` 表示标题级别 (快捷键 Ctrl+1 ~ Ctrl+6)。

## 3. 列表

- 无序列表项
- 另一项
    - 嵌套项 (Tab 缩进)

1. 有序列表
2. 第二项

- [x] 已完成的任务
- [ ] 未完成的任务

## 4. 表格

| 功能       | 快捷键     |  是否支持 |
| :--------- | :--------: | --------: |
| 插入表格   |  Ctrl+T    |        ✔ |
| 对齐表格   | Ctrl+Alt+T |        ✔ |
| 中文对齐   |     —      |        ✔ |

第二行的冒号控制对齐方式: `:---` 左对齐, `:---:` 居中, `---:` 右对齐。

## 5. 图片

![示例图片]({image_path})

语法: `![说明文字](图片路径)`。可以使用相对路径 (相对于 .md 文件)、绝对路径或网络地址。
也可以直接 **Ctrl+V 粘贴截图**, 或把图片文件 **拖进编辑区**。

## 6. 链接

[Markdown 教程](https://commonmark.org/help/) · [跳到表格](#4-表格)

## 7. 引用

> 引用的文字
> 可以有多行

## 8. 代码块

```python
def hello(name: str) -> None:
    print(f"你好, {{name}}!")
```

## 9. 分割线与脚注

---

这里有一个脚注[^1]。

[^1]: 脚注内容会显示在文档末尾。
"""
