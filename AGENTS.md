# AGENTS.md — 维护者指南

给接手维护本项目的人 / AI agent 看的说明。面向用户的介绍在 [README.md](README.md)。
本文件记录的是**代码里看不出来、但改错了会坏**的东西。

## 项目概况

MDReader 是一个 Windows 桌面 Markdown 编辑器：左侧编辑、右侧实时预览，重点是表格和图片正确渲染，
用 PyInstaller 打包成单文件 `MDReader.exe`。

- 技术栈：Python 3.11+、PyQt6（≥6.5，开发时用 6.12）、markdown-it-py + mdit-py-plugins、Pygments、PyInstaller
- 仓库：https://github.com/xkn123/MDReader （exe 通过 GitHub Releases 发布，不进 git）
- 界面文字、README、代码注释都是**简体中文**，新增内容保持一致
- 许可证：源码 MIT；exe 因打包 PyQt6 整体受 GPL v3 约束（README 已说明）

## 环境与常用命令

依赖装在哪个 Python 里很重要：开发机上有多个 Python，`PATH` 里第一个不一定装了 PyQt6。
先确认 `python -c "import PyQt6"` 能通过，否则换用装了依赖的那个解释器（或建 venv）。

```bash
pip install -r requirements-dev.txt     # 运行依赖 + pytest
python main.py examples/demo.md         # 从源码运行
python -m pytest                        # 跑测试 (约 3 秒, 无界面, 不需要显示器)
build.bat                               # 打包 dist\MDReader.exe (单文件, 约 57 MB)
powershell -ExecutionPolicy Bypass -File build.ps1 -OneDir   # 文件夹版, 启动更快
```

`build.ps1` 用的是 `PATH` 上的 `python`，打包前同样要确认它是正确的解释器。

## 架构

```
main.py → mdreader/app.py: run()      QApplication、中文翻译、主题、命令行打开文件
  └─ mainwindow.py: MainWindow         菜单/工具栏/状态栏、文件操作、导出、打印、格式命令
       ├─ editor.py: MarkdownEditor    QPlainTextEdit: 行号、回车续写列表、缩进、行操作、粘贴/拖放
       │    └─ highlighter.py          编辑区语法高亮 (QSyntaxHighlighter)
       ├─ preview.py: PreviewBrowser   QTextBrowser 预览; RenderDocument 用于打印/PDF
       │    └─ images.py: ImageProvider  图片解析/加载/缩放/占位图, 网络图片异步下载
       ├─ renderer.py                  Markdown → HTML (两种风格, 见下)
       ├─ tableformat.py               表格对齐 (纯函数)
       ├─ fileio.py                    编码识别与原子写入 (纯函数)
       ├─ dialogs.py                   查找替换、插入表格、插入链接
       ├─ themes.py                    Theme 数据类: LIGHT / DARK; apply_app_theme
       └─ icon.py                      程序图标 (代码绘制)
tools/make_assets.py                   生成 assets/app.ico、app.png 和 examples/images/*
```

**预览数据流**：编辑器 `textChanged` → 250 ms 单次定时器 → `MainWindow.render_preview()` →
`renderer.render_qt(text, theme, pt)` → `preview.setHtml()` → Qt 对每个 `<img>` 调用
`PreviewBrowser.loadResource()` → `ImageProvider.image(src, 可用宽度)`。
网络图片下载完成后发 `remoteImageLoaded`，再触发一次渲染。渲染前后会保存/恢复滚动位置（或按同步滚动比例对齐）。

**多窗口**：模块级 `_windows` 列表保存所有窗口；主题是全局的（`set_global_theme` 会通知所有窗口）。

**设置**：`QSettings()`（Windows 注册表 `HKCU\Software\MDReader\MDReader`）。键名：
`theme, geometry, windowState, splitter, viewMode, wordWrap, lineNumbers, syncScroll, zoom,
editorFont, editorFontSize, lastDir, recentFiles`。

## 两种渲染风格（renderer.py）

| | `render_qt` | `render_web` / `export_html` |
|---|---|---|
| 用途 | 程序内预览、打印、PDF | 导出 HTML 文件，在浏览器中看 |
| 限制 | 只能用 Qt 富文本支持的 HTML/CSS 子集 | 标准 HTML + `WEB_CSS`（GitHub 风格） |

QTextBrowser **不是浏览器**：不支持 `border-left`、`border-radius`、大多数 `padding`/`margin` 组合、
`id` 锚点、`<input>`、CSS 类选择器的完整语义、JavaScript 等。所以 Qt 风格里：

- 代码块 → 单格 `<table bgcolor>` 包 `<pre>`；Pygments 用 `noclasses=True` 输出行内颜色
- 引用 → 两格表格，窄的那格上色当左边竖线
- 表格 → `border="1"` + `border-collapse`；斑马纹写在偶数行 `td` 的 `style` 上
- 分割线 → 2px 高的单格表格
- 标题 `id` → `_ids_to_anchors()` 转成 `<a name>`（Qt 只认 name 锚点）
- 任务列表 → ☑ / ☐ 字符（Qt 不渲染 `<input type=checkbox>`）
- 以行内元素开头的 HTML 块（如单独一行 `<img width=300>`）→ 包一层 `<p>`，否则 Qt 会把它并进上一段

修改 Qt 风格的输出后，**一定要截图看实际效果**（见下文“手动验证”），单元测试只能检查 HTML 字符串。

## 不变量与坑（改代码前先读）

1. **文本位置是 UTF-16**。Qt 的光标位置按 UTF-16 码元计，emoji 等非 BMP 字符占 2；Python 下标占 1。
   涉及位置换算一律用 `editor.u16len()`（编辑器、格式命令）或 `dialogs._PosMap`（查找替换）。
   已有 emoji 相关测试，改动后跑测试。
2. **`QTextCursor.selectedText()` 里的换行是 U+2029**（段落分隔符），不是 `\n`。代码中
   `.replace(" ", "\n")` 处的那个字符就是 U+2029，编辑时不要把它“修正”成空格。
3. **编辑操作要包在 `beginEditBlock()/endEditBlock()` 里**，保证一次撤销就能还原（全部替换、表格对齐、移动行等）。
4. **图片 URL**：markdown-it 会把 Markdown 图片地址百分号编码（`a b.png` → `a%20b.png`）；
   `ImageProvider.resolve()` 负责 `unquote`、去掉 `?query`/`#fragment`（文件真实存在时除外）、
   处理 `/` 开头（先按文档目录找）、Windows 绝对路径、UNC、`file:`、`data:`。
5. **打印 / PDF 的图片**：`RenderDocument.loadResource()` 必须调用 `addResource()`，因为打印时
   `QTextDocument.print()` 会 clone 文档，clone 只保留已加入资源的图片；`prepare()` 强制排版以确保图片都加载过。
   打印不会发起网络请求（`allow_fetch=False`），只有已缓存的网络图片会出现。打印/PDF 固定使用 LIGHT 主题、A4、16 mm 边距。
6. **QSyntaxHighlighter 要保留 Python 引用**（`MainWindow.highlighter`），否则会被垃圾回收、高亮失效。
   块状态 `1` 表示“在代码围栏内”。
7. **文件读写**：`fileio.read_text_file` 把换行统一成 `\n` 放进编辑器，记录原编码/BOM/换行符；
   保存时按原样写回（`write_text_file` 先写临时文件再 `os.replace`）。不要在其他地方直接 `open().write()` 文档。
8. **链接点击**：`PreviewBrowser.setOpenLinks(False)`，所有链接由 `MainWindow._on_link` 处理
   （`#锚点` 滚动、http 用系统浏览器、本地 .md 在程序内打开）。
9. **主题**：`Theme` 是冻结数据类，新增颜色字段必须同时给 `LIGHT` 和 `DARK` 赋值。
   深色模式下应用用 Fusion 风格 + 深色调色板；浅色用系统原生风格。
10. **会弹模态对话框的路径**：`export_html`、`maybe_save`/`closeEvent`（文档有修改时）、
    未保存文档粘贴图片、`print_doc`、`print_preview` 等。测试里调用这些会卡死；要么避开，要么先 `setModified(False)`。
    `export_pdf(path, ask_open=False)` 是可以在测试里安全调用的。
11. **不要引入 QtWebEngine**：会让 exe 从 ~57 MB 涨到 200 MB 以上，这是刻意的取舍。
    因此不支持 LaTeX、Mermaid、JavaScript（README 已写明）。

## 打包（build.ps1）注意事项

- `--hidden-import PyQt6.QtSvg`：否则 SVG 图片不显示（还需要 `qsvg` 图像插件，PyInstaller 会随 QtSvg 带上）。
- `--collect-submodules pygments.lexers / pygments.styles`：Pygments 按名称动态导入，不收集的话 exe 里代码高亮全部失效。
- 中文翻译 `qtbase_zh_CN.qm`：`app._install_translations` 在打包后从 `sys._MEIPASS/PyQt6/Qt6/translations` 加载。
- `build.ps1` **必须保存为 UTF-8 带 BOM**，否则 Windows PowerShell 5.1 会把里面的中文读乱导致语法错误。
- 单文件 exe 实际是两个进程（引导程序 + 程序本身），只有子进程有窗口；自动化截图时要找
  `MainWindowHandle` 非零的那个 `MDReader` 进程。首次启动约 10 秒，之后约 4 秒。
- `assets/` 和 `examples/images/` 由 `tools/make_assets.py` 生成并已提交；改图标改 `mdreader/icon.py` 后重新运行它。

## 测试

`tests/` 下是 pytest 测试，以 `QT_QPA_PLATFORM=offscreen` 无界面运行，`QSettings` 被重定向到临时 INI 文件
（不会改动真实用户设置）。共享夹具在 `tests/conftest.py`（`qapp`、`png_file`）。

| 文件 | 覆盖内容 |
|---|---|
| `test_tableformat.py` | 显示宽度（中文双宽）、拆分单元格、对齐、跳过代码块 |
| `test_fileio.py` | 各编码 / BOM / 换行符往返、GBK 识别、强制编码、原子写入 |
| `test_renderer.py` | Qt 与网页两种输出的结构：表格、代码、引用、任务、锚点、图片路径改写 |
| `test_images.py` | 路径解析、本地/SVG/data URI 加载、缩放、占位图 |
| `test_editor.py` | 回车续写、Tab 缩进、移动/复制/删除行（含 emoji）、高亮器代码块状态 |
| `test_dialogs.py` | 查找替换（emoji 位置、大小写、全字、正则分组、一次撤销） |
| `test_mainwindow.py` | 打开 demo、粗体/标题/列表切换、表格对齐命令、GBK 保存往返、PDF 导出含图片 |

修 bug 时先写一个能复现的测试。新增纯逻辑尽量放进无 Qt 依赖的模块（如 `tableformat.py`、`fileio.py`）以便测试。

**测试覆盖不到、改动相关代码后需要手动验证的**：预览的实际视觉效果（颜色、间距、深色主题）、打印预览对话框、
网络图片加载、拖放文件、剪贴板粘贴截图、外部修改文件后的自动重载、exe 打包后的行为。
截图方法：创建窗口后 `setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)`、`show()`、处理事件，
再用 `window.grab().save("x.png")` 保存图片查看；用 `examples/demo.md` 作为输入，它覆盖了所有渲染特性。

## 发布新版本

1. 改版本号：`mdreader/__init__.py` 的 `__version__`，以及 `version_info.txt` 里的 `filevers`、`prodvers`、
   `FileVersion`、`ProductVersion`（四处）。
2. `python -m pytest` 全部通过。
3. `build.bat` 重新打包，运行 `dist\MDReader.exe examples\demo.md` 确认能启动、表格图片正常、代码有高亮。
4. 提交并推送，然后发布：
   `gh release create vX.Y.Z dist/MDReader.exe --title "MDReader vX.Y.Z" --notes "更新内容"`

`build/`、`dist/`、`*.spec` 已在 `.gitignore` 中，exe 不进 git。
