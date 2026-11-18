"""生成程序图标 (assets/app.ico) 和示例图片 (examples/images/*)。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QRectF, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPen  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from mdreader.icon import make_icon_image, write_ico  # noqa: E402


def make_chart(path: str) -> None:
    w, h = 720, 360
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setFont(QFont("Microsoft YaHei UI", 16, QFont.Weight.Bold))
    p.setPen(QColor("#1f2328"))
    p.drawText(QRectF(0, 12, w, 36), Qt.AlignmentFlag.AlignCenter, "季度销售额 (示例图片)")
    data = [("Q1", 120, "#3b82f6"), ("Q2", 180, "#10b981"), ("Q3", 150, "#f59e0b"), ("Q4", 220, "#ef4444")]
    base_y, left, bw, gap = h - 50, 90, 90, 60
    p.setPen(QPen(QColor("#d0d7de"), 1))
    for i in range(5):
        y = base_y - i * 55
        p.drawLine(left - 20, y, w - 40, y)
    p.setFont(QFont("Microsoft YaHei UI", 11))
    for i, (label, val, color) in enumerate(data):
        x = left + i * (bw + gap)
        top = base_y - val
        grad = QLinearGradient(x, top, x, base_y)
        grad.setColorAt(0, QColor(color).lighter(120))
        grad.setColorAt(1, QColor(color))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(QRectF(x, top, bw, val), 6, 6)
        p.setPen(QColor("#1f2328"))
        p.drawText(QRectF(x, base_y + 6, bw, 24), Qt.AlignmentFlag.AlignCenter, label)
        p.drawText(QRectF(x, top - 26, bw, 22), Qt.AlignmentFlag.AlignCenter, f"{val} 万")
    p.end()
    img.save(path, "PNG")


SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="260" height="120" viewBox="0 0 260 120">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#8b5cf6"/><stop offset="1" stop-color="#ec4899"/></linearGradient></defs>
  <rect x="2" y="2" width="256" height="116" rx="18" fill="url(#g)"/>
  <circle cx="60" cy="60" r="30" fill="#ffffff" opacity="0.9"/>
  <polygon points="110,90 150,30 190,90" fill="#ffffff" opacity="0.85"/>
  <rect x="200" y="35" width="40" height="50" rx="6" fill="#ffffff" opacity="0.75"/>
</svg>
"""


def main() -> None:
    app = QApplication(sys.argv)  # noqa: F841  QPainter 文字渲染需要
    os.makedirs(os.path.join(ROOT, "assets"), exist_ok=True)
    write_ico(os.path.join(ROOT, "assets", "app.ico"))
    make_icon_image(256).save(os.path.join(ROOT, "assets", "app.png"), "PNG")
    img_dir = os.path.join(ROOT, "examples", "images")
    os.makedirs(img_dir, exist_ok=True)
    make_chart(os.path.join(img_dir, "chart.png"))
    with open(os.path.join(img_dir, "shapes.svg"), "w", encoding="utf-8") as f:
        f.write(SVG)
    make_icon_image(96).save(os.path.join(img_dir, "logo 图标.png"), "PNG")
    print("assets generated")


if __name__ == "__main__":
    main()
