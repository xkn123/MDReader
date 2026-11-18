"""预览窗口与用于打印 / PDF 的渲染文档。"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QFont, QTextDocument
from PyQt6.QtWidgets import QTextBrowser

from .images import ImageProvider

_IMAGE = QTextDocument.ResourceType.ImageResource.value
UI_FONTS = ["Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei"]


def _rt(rtype) -> int:
    return rtype.value if hasattr(rtype, "value") else int(rtype)


def body_font(pt: int) -> QFont:
    f = QFont()
    f.setFamilies(UI_FONTS)
    f.setPointSize(pt)
    return f


class PreviewBrowser(QTextBrowser):
    widthChanged = pyqtSignal()
    zoomRequested = pyqtSignal(int)

    def __init__(self, provider: ImageProvider, parent=None) -> None:
        super().__init__(parent)
        self.provider = provider
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self._last_width = 0
        self.document().setDocumentMargin(24)

    def max_image_width(self) -> int:
        return max(80, self.viewport().width() - 70)

    def loadResource(self, rtype, name: QUrl):
        if _rt(rtype) == _IMAGE:
            return self.provider.image(name.toString(), self.max_image_width())
        return super().loadResource(rtype, name)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        w = self.viewport().width()
        if abs(w - self._last_width) > 6:
            self._last_width = w
            self.widthChanged.emit()

    def wheelEvent(self, e) -> None:
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoomRequested.emit(1 if e.angleDelta().y() > 0 else -1)
            e.accept()
            return
        super().wheelEvent(e)


class RenderDocument(QTextDocument):
    """离屏文档, 用于打印 / 导出 PDF。图片会被加入资源以便在复制文档时保留。"""

    def __init__(self, provider: ImageProvider, max_width: int, parent=None) -> None:
        super().__init__(parent)
        self.provider = provider
        self.max_width = max_width

    def loadResource(self, rtype, name: QUrl):
        if _rt(rtype) == _IMAGE:
            img = self.provider.image(name.toString(), self.max_width, allow_fetch=False)
            self.addResource(_IMAGE, name, img)
            return img
        return super().loadResource(rtype, name)

    def prepare(self, width: int) -> None:
        """强制完成排版, 确保所有图片都已加载。"""
        self.setTextWidth(width)
        self.documentLayout().documentSize()
        self.pageCount()
