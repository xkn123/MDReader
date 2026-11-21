import codecs

import pytest

from mdreader.fileio import TextFileInfo, encoding_label, read_text_file, write_text_file

TEXT = "# 标题\n\n中文 English 😀\n"


@pytest.mark.parametrize("encoding,bom,newline", [
    ("utf-8", False, "\n"),
    ("utf-8", True, "\r\n"),
    ("utf-16", True, "\n"),
    ("gb18030", False, "\r\n"),
])
def test_roundtrip_preserves_encoding_bom_and_newline(tmp_path, encoding, bom, newline):
    text = TEXT if encoding != "gb18030" else TEXT.replace("😀", "")
    p = tmp_path / "f.md"
    write_text_file(str(p), TextFileInfo(text, encoding, bom, newline))
    raw = p.read_bytes()
    if encoding == "utf-8":
        assert raw.startswith(codecs.BOM_UTF8) == bom
    if newline == "\r\n":
        assert b"\r\n" in raw or encoding == "utf-16"
    info = read_text_file(str(p))
    assert info.text == text            # newlines are normalised to \n in memory
    assert (info.encoding, info.bom, info.newline) == (encoding, bom, newline)


def test_gbk_file_detected(tmp_path):
    p = tmp_path / "gbk.md"
    p.write_bytes("你好，世界".encode("gbk"))
    info = read_text_file(str(p))
    assert info.encoding == "gb18030"
    assert info.text == "你好，世界"


def test_force_encoding_overrides_detection(tmp_path):
    p = tmp_path / "f.md"
    p.write_bytes("你好".encode("utf-8"))
    info = read_text_file(str(p), force_encoding="gb18030")
    assert info.encoding == "gb18030"
    assert info.text != "你好"


def test_lone_cr_is_normalised(tmp_path):
    p = tmp_path / "f.md"
    p.write_bytes(b"a\rb\r\nc")
    assert read_text_file(str(p)).text == "a\nb\nc"


def test_write_leaves_no_temp_files(tmp_path):
    p = tmp_path / "f.md"
    write_text_file(str(p), TextFileInfo("x"))
    write_text_file(str(p), TextFileInfo("y"))
    assert [f.name for f in tmp_path.iterdir()] == ["f.md"]
    assert p.read_text(encoding="utf-8") == "y"


def test_encoding_label():
    assert encoding_label("utf-8", True) == "UTF-8 BOM"
    assert encoding_label("gb18030", False) == "GBK/GB18030"
