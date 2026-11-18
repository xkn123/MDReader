"""程序图标 (运行时绘制, 无需外部文件)。"""
from __future__ import annotations

import struct

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PyQt6.QtGui import (QColor, QFont, QIcon, QImage, QLinearGradient, QPainter,
                         QPainterPath, QPen, QPixmap)


def make_icon_image(size: int = 256) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    m = size * 0.06
    rect = QRectF(m, m, size - 2 * m, size - 2 * m)
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0, QColor("#3b82f6"))
    grad.setColorAt(1, QColor("#1d4ed8"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(rect, size * 0.2, size * 0.2)

    # 绘制 "M↓" 标志 (用路径绘制, 不依赖字体)
    w = rect.width()
    pen = QPen(QColor("white"), max(1.5, w * 0.085))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    x0, y0 = rect.left() + w * 0.18, rect.top() + w * 0.30
    x1, y1 = rect.left() + w * 0.56, rect.top() + w * 0.70
    path = QPainterPath(QPointF(x0, y1))
    path.lineTo(x0, y0)
    path.lineTo((x0 + x1) / 2, y0 + (y1 - y0) * 0.45)
    path.lineTo(x1, y0)
    path.lineTo(x1, y1)
    p.drawPath(path)
    ax = rect.left() + w * 0.78
    p.drawLine(QPointF(ax, y0), QPointF(ax, y1))
    arrow = QPainterPath(QPointF(ax - w * 0.11, y1 - w * 0.12))
    arrow.lineTo(ax, y1)
    arrow.lineTo(ax + w * 0.11, y1 - w * 0.12)
    p.drawPath(arrow)
    p.end()
    return img


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(make_icon_image(s)))
    return icon


def write_ico(path: str, sizes=(16, 24, 32, 48, 64, 128, 256)) -> None:
    """写出包含多个尺寸 (PNG 压缩) 的 .ico 文件。"""
    blobs = []
    for s in sizes:
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        make_icon_image(s).save(buf, "PNG")
        buf.close()
        blobs.append((s, bytes(ba)))
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries, data = b"", b""
    for s, png in blobs:
        dim = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    with open(path, "wb") as f:
        f.write(header + entries + data)
