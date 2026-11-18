"""文本文件读写: 自动识别编码 (UTF-8 / UTF-8 BOM / UTF-16 / GB18030) 与换行符。"""
from __future__ import annotations

import codecs
import os
import tempfile
from dataclasses import dataclass


@dataclass
class TextFileInfo:
    text: str
    encoding: str = "utf-8"   # utf-8 / utf-16 / gb18030
    bom: bool = False
    newline: str = "\n"


ENCODING_LABELS = {
    ("utf-8", False): "UTF-8",
    ("utf-8", True): "UTF-8 BOM",
    ("utf-16", True): "UTF-16",
    ("gb18030", False): "GBK/GB18030",
}


def encoding_label(encoding: str, bom: bool) -> str:
    return ENCODING_LABELS.get((encoding, bom), encoding.upper())


def read_text_file(path: str, force_encoding: str | None = None) -> TextFileInfo:
    with open(path, "rb") as f:
        data = f.read()
    bom = False
    if force_encoding:
        enc = force_encoding
        if enc == "utf-8" and data.startswith(codecs.BOM_UTF8):
            data, bom = data[3:], True
        text = data.decode(enc, errors="replace")
    elif data.startswith(codecs.BOM_UTF8):
        enc, bom, text = "utf-8", True, data[3:].decode("utf-8", errors="replace")
    elif data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        enc, bom, text = "utf-16", True, data.decode("utf-16", errors="replace")
    else:
        try:
            enc, text = "utf-8", data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                enc, text = "gb18030", data.decode("gb18030")
            except UnicodeDecodeError:
                enc, text = "utf-8", data.decode("utf-8", errors="replace")
    newline = "\r\n" if "\r\n" in text else "\n"
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return TextFileInfo(text, enc, bom, newline)


def write_text_file(path: str, info: TextFileInfo) -> None:
    text = info.text.replace("\n", info.newline) if info.newline != "\n" else info.text
    if info.encoding == "utf-16":
        data = text.encode("utf-16")  # 自带 BOM
    else:
        data = text.encode(info.encoding)
        if info.bom and info.encoding == "utf-8":
            data = codecs.BOM_UTF8 + data
    folder = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".mdreader-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        try:
            os.replace(tmp, path)
        except PermissionError:
            # 目标被占用时退回到直接写入
            with open(path, "wb") as f:
                f.write(data)
            os.remove(tmp)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
