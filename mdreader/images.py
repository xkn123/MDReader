"""图片加载: 本地相对 / 绝对路径、file://、data: URI 以及网络图片 (异步下载)。"""
from __future__ import annotations

import base64
import os
import re
from urllib.parse import unquote

from PyQt6.QtCore import QObject, QRectF, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QImageReader, QPainter, QPen
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

WIN_ABS_RE = re.compile(r"^[a-zA-Z]:[\\/]")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico",
              ".tif", ".tiff"}


class ImageProvider(QObject):
    """为预览 / 打印提供图片, 并按可用宽度缩放。"""

    remoteImageLoaded = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.base_dir = ""
        self._local: dict[str, tuple[float, QImage]] = {}
        self._remote: dict[str, QImage] = {}
        self._pending: set[str] = set()
        self._nam = QNetworkAccessManager(self)
        self._nam.finished.connect(self._on_finished)

    # ------------------------------------------------------------------
    def resolve(self, src: str) -> tuple[str, str]:
        """返回 (类型, 值); 类型为 data / remote / local。"""
        s = src.strip()
        low = s.lower()
        if low.startswith("data:"):
            return "data", s
        if low.startswith(("http://", "https://")):
            return "remote", s
        if low.startswith("file:"):
            return "local", os.path.normpath(QUrl(s).toLocalFile())
        s = unquote(s)
        # 去掉查询串 / 片段
        for sep in ("?", "#"):
            if sep in s and not os.path.exists(os.path.join(self.base_dir or "", s)):
                s = s.split(sep, 1)[0]
        if WIN_ABS_RE.match(s) or s.startswith("\\\\"):
            return "local", os.path.normpath(s)
        base = self.base_dir or os.getcwd()
        if s.startswith("/"):
            candidate = os.path.normpath(os.path.join(base, s.lstrip("/")))
            if os.path.exists(candidate):
                return "local", candidate
            return "local", os.path.normpath(s)
        return "local", os.path.normpath(os.path.join(base, s))

    def image(self, src: str, max_width: int, allow_fetch: bool = True) -> QImage:
        kind, value = self.resolve(src)
        if kind == "data":
            img = self._decode_data(value)
            if img.isNull():
                return placeholder("无法解析 data URI 图片")
        elif kind == "remote":
            if value in self._remote:
                img = self._remote[value]
                if img.isNull():
                    return placeholder(f"网络图片加载失败: {value}")
            else:
                if allow_fetch:
                    self._fetch(value)
                return placeholder(f"正在加载网络图片… {value}")
        else:
            img = self._load_local(value)
            if img is None:
                return placeholder(f"找不到图片: {value}")
        return fit_width(img, max_width)

    def local_path(self, src: str) -> str | None:
        kind, value = self.resolve(src)
        return value if kind == "local" else None

    # ------------------------------------------------------------------
    def _load_local(self, path: str) -> QImage | None:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return None
        cached = self._local.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        img = reader.read()
        if img.isNull():
            return None
        self._local[path] = (mtime, img)
        return img

    @staticmethod
    def _decode_data(uri: str) -> QImage:
        try:
            header, data = uri.split(",", 1)
            raw = base64.b64decode(data) if ";base64" in header else unquote(data).encode("utf-8")
            img = QImage()
            img.loadFromData(raw)
            return img
        except Exception:
            return QImage()

    def _fetch(self, url: str) -> None:
        if url in self._pending:
            return
        self._pending.add(url)
        req = QNetworkRequest(QUrl(url))
        req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader,
                      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MDReader/1.0")
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        req.setTransferTimeout(20000)
        reply = self._nam.get(req)
        reply.setProperty("mdr_src", url)

    def _on_finished(self, reply: QNetworkReply) -> None:
        url = reply.property("mdr_src")
        img = QImage()
        if reply.error() == QNetworkReply.NetworkError.NoError:
            img.loadFromData(bytes(reply.readAll()))
        reply.deleteLater()
        if url is None:
            return
        self._pending.discard(url)
        self._remote[url] = img
        self.remoteImageLoaded.emit()

    def clear_cache(self) -> None:
        self._local.clear()
        self._remote = {k: v for k, v in self._remote.items() if not v.isNull()}


def fit_width(img: QImage, max_width: int) -> QImage:
    if max_width > 0 and img.width() > max_width:
        return img.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
    return img


def placeholder(text: str, width: int = 420, height: int = 46) -> QImage:
    img = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor("#f3f4f6"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor("#c4c9cf"), 1, Qt.PenStyle.DashLine))
    p.drawRect(QRectF(0.5, 0.5, width - 1, height - 1))
    font = QFont("Microsoft YaHei UI", 9)
    p.setFont(font)
    p.setPen(QColor("#6e7781"))
    fm = p.fontMetrics()
    shown = fm.elidedText("🖼  " + text, Qt.TextElideMode.ElideMiddle, width - 20)
    p.drawText(QRectF(10, 0, width - 20, height),
               Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, shown)
    p.end()
    return img
