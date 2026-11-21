import base64
import os

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QUrl
from PyQt6.QtGui import QColor, QImage

from mdreader.images import ImageProvider, fit_width, placeholder


def test_resolve_kinds(qapp, tmp_path):
    p = ImageProvider()
    p.base_dir = str(tmp_path)
    assert p.resolve("data:image/png;base64,xx")[0] == "data"
    assert p.resolve("https://example.com/a.png") == ("remote", "https://example.com/a.png")
    assert p.resolve("img/a.png") == ("local", os.path.normpath(os.path.join(tmp_path, "img/a.png")))
    assert p.resolve("logo%20%E5%9B%BE.png")[1].endswith("logo 图.png")
    assert p.resolve("a.png?v=2")[1].endswith("a.png")
    assert p.resolve(r"C:\x\y.png") == ("local", os.path.normpath(r"C:\x\y.png"))
    url = QUrl.fromLocalFile(str(tmp_path / "z.png")).toString()
    assert p.resolve(url) == ("local", os.path.normpath(str(tmp_path / "z.png")))


def test_local_image_is_loaded_and_scaled(qapp, png_file):
    p = ImageProvider()
    p.base_dir = os.path.dirname(png_file)
    img = p.image("pic.png", max_width=1000)
    assert (img.width(), img.height()) == (200, 100)
    small = p.image("pic.png", max_width=50)
    assert (small.width(), small.height()) == (50, 25)


def test_missing_image_returns_placeholder(qapp, tmp_path):
    p = ImageProvider()
    p.base_dir = str(tmp_path)
    img = p.image("nope.png", 800)
    assert not img.isNull()
    assert (img.width(), img.height()) == (420, 46)


def test_data_uri(qapp):
    src = QImage(10, 6, QImage.Format.Format_RGB32)
    src.fill(QColor("blue"))
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    src.save(buf, "PNG")
    uri = "data:image/png;base64," + base64.b64encode(bytes(ba)).decode()
    img = ImageProvider().image(uri, 100)
    assert (img.width(), img.height()) == (10, 6)


def test_remote_without_fetch_is_placeholder(qapp):
    p = ImageProvider()
    img = p.image("https://example.invalid/x.png", 500, allow_fetch=False)
    assert (img.width(), img.height()) == (420, 46)
    assert not p._pending


def test_svg_example_loads(qapp):
    # Needs the Qt SVG image plugin; the exe build must bundle it too.
    p = ImageProvider()
    p.base_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples")
    img = p.image("images/shapes.svg", 2000)
    assert (img.width(), img.height()) != (420, 46)


def test_fit_width_and_placeholder(qapp):
    big = QImage(400, 200, QImage.Format.Format_RGB32)
    assert fit_width(big, 0).width() == 400
    assert fit_width(big, 100).height() == 50
    assert placeholder("x", 100, 20).size().width() == 100
