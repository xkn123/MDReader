# MDReader — Markdown 阅读 / 编辑器

一个 Windows 图形界面的 Markdown 编辑器：左侧编辑源码，右侧实时预览，**表格**和**图片**都能正确渲染。

**下载**：到 [Releases](../../releases) 页面下载 `MDReader.exe`（单文件，无需安装 Python，双击即可运行）。
也可以按下文说明从源码运行或自行编译。

## 功能

**渲染**
- CommonMark 标准语法 + GitHub 风格表格（支持左 / 中 / 右对齐、斑马纹）、删除线、任务列表、脚注
- 图片：相对路径、绝对路径、`file://`、网络图片（异步下载）、`data:` URI，支持 PNG / JPG / GIF / BMP / WebP / SVG；
  大图自动缩放到窗口宽度；可用 `<img width="300">` 指定尺寸；找不到的图片显示占位提示
- 代码块语法高亮（Pygments，支持数百种语言）
- 标题锚点跳转（`[跳转](#标题)`）、点击链接打开网页 / 其他 .md 文件
- 浅色 / 深色主题

**编辑**
- 新建、打开（多选）、保存、另存为、重新载入、最近打开的文件、多窗口
- 撤销 / 重做、剪切 / 复制 / 粘贴、全选
- 查找、替换（区分大小写、全字匹配、正则表达式、全部替换）、转到行
- Markdown 语法高亮、行号、当前行高亮、自动换行开关
- 回车自动续写列表 / 引用，空列表项回车结束列表；Tab / Shift+Tab 缩进
- 复制行、删除行、上下移动行、大小写转换、插入日期时间
- 格式工具栏：粗体、斜体、删除线、标题 1–6、引用、列表、任务、代码、链接、图片、表格、分割线
- **表格自动对齐**（Ctrl+Alt+T，中文按双宽度对齐）
- **Ctrl+V 粘贴截图**：自动保存到文档目录的 `images/` 并插入引用
- 拖入图片文件 → 插入图片；拖入 .md 文件 → 打开
- 外部修改自动检测并重新载入；关闭时提示保存未保存的修改
- 自动识别编码（UTF-8 / UTF-8 BOM / UTF-16 / GBK），可选择保存编码和换行符（CRLF / LF）
- 状态栏：行列号、字数（中英文分别统计）、字符数、编码、换行符、缩放比例

**输出**
- 导出 HTML（可选把图片嵌入为单个独立文件）
- 导出 PDF、打印、打印预览

**视图**：仅编辑 / 分屏 / 仅预览（阅读模式）、同步滚动、Ctrl+滚轮缩放、全屏（F11）

## 常用快捷键

| 功能 | 快捷键 | 功能 | 快捷键 |
| :--- | :--- | :--- | :--- |
| 新建 / 打开 / 保存 | Ctrl+N / Ctrl+O / Ctrl+S | 另存为 | Ctrl+Shift+S |
| 查找 / 替换 | Ctrl+F / Ctrl+H | 查找下一个 / 上一个 | F3 / Shift+F3 |
| 转到行 | Ctrl+G | 打印 | Ctrl+P |
| 粗体 / 斜体 | Ctrl+B / Ctrl+I | 行内代码 | Ctrl+` |
| 标题 1–6 | Ctrl+1 … Ctrl+6 | 链接 / 图片 | Ctrl+K / Ctrl+Shift+I |
| 插入表格 | Ctrl+T | 对齐表格 | Ctrl+Alt+T |
| 仅编辑 / 分屏 / 仅预览 | Ctrl+Alt+1 / 2 / 3 | 深色主题 | Ctrl+Shift+D |
| 放大 / 缩小 / 重置 | Ctrl+= / Ctrl+- / Ctrl+0 | 语法示例 | F1 |

## 从源码运行

```bash
pip install -r requirements.txt
python main.py examples/demo.md
```

## 编译 exe

```bash
build.bat
```

或在 PowerShell 中运行 `build.ps1`。生成 `dist\MDReader.exe`（约 57 MB）。
单文件 exe 每次启动需要先解压，约 3–5 秒；如果想启动更快，可以编译文件夹版：

```bash
powershell -ExecutionPolicy Bypass -File build.ps1 -OneDir
```

生成 `dist\MDReader\` 文件夹，运行其中的 `MDReader.exe`。

**设为 .md 默认打开方式**：右键任意 .md 文件 → 打开方式 → 选择其他应用 → 在电脑上选择应用 → 选中 `MDReader.exe` → 始终使用。

## 项目结构

```
main.py                 启动入口
mdreader/
  app.py                QApplication 初始化、命令行参数、中文翻译
  mainwindow.py         主窗口：菜单、工具栏、文件操作、导出、打印
  editor.py             编辑器：行号、列表续写、缩进、粘贴 / 拖放图片
  highlighter.py        编辑区 Markdown 语法高亮
  preview.py            预览控件（QTextBrowser）与打印用文档
  renderer.py           Markdown → HTML（markdown-it-py + Pygments）
  images.py             图片加载（本地 / 网络 / data URI）与缩放
  tableformat.py        表格对齐
  fileio.py             编码识别与保存
  dialogs.py            查找替换、插入表格、插入链接对话框
  themes.py             浅色 / 深色配色
  icon.py               程序图标（代码绘制）
tools/make_assets.py    生成 assets/app.ico 和示例图片
examples/demo.md        演示文档（表格、图片、代码等）
```

## 说明

预览使用 Qt 自带的富文本引擎（不内置浏览器内核），所以 exe 体积小。因此**不支持**
JavaScript、数学公式（LaTeX）和 Mermaid 图表；复杂的 CSS 排版会被简化显示。

## 许可证

本项目源码以 [MIT License](LICENSE) 发布。

依赖的第三方库各自遵循其许可证：PyQt6（GPL v3）、markdown-it-py / mdit-py-plugins（MIT）、
Pygments（BSD）。由于编译出的 exe 打包了 PyQt6，**分发的 exe 整体须遵守 GPL v3**；
源码本身仍可按 MIT 使用。
