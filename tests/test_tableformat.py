from mdreader.tableformat import (display_width, find_tables, format_all_tables,
                                  format_table, make_table, split_row)


def test_display_width_counts_cjk_as_double():
    assert display_width("abc") == 3
    assert display_width("中文") == 4
    assert display_width("a中b") == 4
    assert display_width("ｅ") == 2          # full-width latin
    assert display_width("é") == 1    # combining accent adds nothing


def test_split_row_handles_escapes_and_inline_code():
    assert split_row("| a | b |") == ["a", "b"]
    assert split_row("a | b") == ["a", "b"]
    assert split_row(r"| a \| b | c |") == [r"a \| b", "c"]
    assert split_row("| `x | y` | z |") == ["`x | y`", "z"]


def test_format_table_aligns_columns_and_keeps_alignment_markers():
    out = format_table(["|名称|数量|说明|", "|:-|-:|:-:|", "|苹果|3|红色的|", "|b|12345|x|"])
    assert out == [
        "| 名称 |  数量 |  说明  |",
        "| :--- | ----: | :----: |",
        "| 苹果 |     3 | 红色的 |",
        "| b    | 12345 |   x    |",
    ]
    # every row has the same display width
    assert len({display_width(l) for l in out}) == 1


def test_format_table_pads_short_rows_and_keeps_indent():
    out = format_table(["  | a | b | c |", "  |---|---|---|", "  | 1 |"])
    assert out[2] == "  | 1   |     |     |"
    assert all(l.startswith("  | ") for l in out)


def test_format_table_rejects_non_tables():
    assert format_table(["| a |"]) is None
    assert format_table(["| a |", "| b |"]) is None


def test_find_tables_skips_code_fences():
    lines = [
        "```", "| a | b |", "|---|---|", "```",
        "", "| x | y |", "|---|---|", "| 1 | 2 |", "", "text",
    ]
    assert find_tables(lines) == [(5, 8)]


def test_format_all_tables_counts_and_rewrites():
    text = "# t\n\n|a|b|\n|-|-|\n|1|22|\n\npara\n\n|c|\n|-|\n"
    new, n = format_all_tables(text)
    assert n == 2
    assert "| a   | b   |" in new          # columns are at least 3 wide
    assert "| 1   | 22  |" in new
    assert new.startswith("# t\n\n") and "\npara\n" in new


def test_make_table_shape():
    t = make_table(2, 3, "center").split("\n")
    assert len(t) == 4
    assert t[0].startswith("| 列1")
    assert t[1].count(":") == 6
