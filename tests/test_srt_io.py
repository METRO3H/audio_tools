from core.translation.srt import SubtitleEntry, parse_srt, write_srt

SAMPLE = (
    "1\n00:00:00,000 --> 00:00:01,000\nHola\n\n"
    "2\n00:00:01,000 --> 00:00:02,000\nLinea uno\nLinea dos\n"
)


def test_parse_basic_and_multiline(tmp_path):
    p = tmp_path / "a.srt"
    p.write_text(SAMPLE, encoding="utf-8")
    entries = parse_srt(p)
    assert [e.index for e in entries] == [1, 2]
    assert entries[0].timestamp == "00:00:00,000 --> 00:00:01,000"
    assert entries[1].lines == ["Linea uno", "Linea dos"]


def test_parse_handles_bom_and_crlf(tmp_path):
    p = tmp_path / "a.srt"
    p.write_bytes(b"\xef\xbb\xbf" + SAMPLE.replace("\n", "\r\n").encode("utf-8"))
    entries = parse_srt(p)
    assert [e.index for e in entries] == [1, 2]
    assert entries[0].lines == ["Hola"]


def test_parse_discards_malformed_blocks(tmp_path):
    p = tmp_path / "a.srt"
    p.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nOK\n\n"
        "solo dos filas\n00:00:01,000 --> 00:00:02,000\n\n"       # < 3 filas
        "abc\n00:00:02,000 --> 00:00:03,000\nindice no numerico\n\n"  # índice inválido
        "4\n00:00:03,000 --> 00:00:04,000\nOtro\n",
        encoding="utf-8",
    )
    assert [e.index for e in parse_srt(p)] == [1, 4]


def test_write_then_parse_roundtrip(tmp_path):
    entries = [
        SubtitleEntry(1, "00:00:00,000 --> 00:00:01,000", ["Hello"]),
        SubtitleEntry(2, "00:00:01,000 --> 00:00:02,000", ["Two", "lines"]),
    ]
    p = tmp_path / "out.srt"
    write_srt(p, entries)
    assert p.read_text(encoding="utf-8") == (
        "1\n00:00:00,000 --> 00:00:01,000\nHello\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\nTwo\nlines\n"
    )
    assert parse_srt(p) == entries
