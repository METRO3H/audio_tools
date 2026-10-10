from core.translation.filenames_runner import FilenameTranslateRunner


def test_sanitize_removes_windows_invalid_chars_and_collapses_spaces():
    assert FilenameTranslateRunner._sanitize('A: "B"  /  C?*') == "A B C"
    assert FilenameTranslateRunner._sanitize('<>:"/\\|?*') == "untitled"
    assert FilenameTranslateRunner._sanitize("   ") == "untitled"


def test_unique_path_appends_counter_before_extension(tmp_path):
    (tmp_path / "x.txt").write_text("1")
    (tmp_path / "x (2).txt").write_text("2")
    assert FilenameTranslateRunner._unique_path(tmp_path / "x.txt") == tmp_path / "x (3).txt"
    assert FilenameTranslateRunner._unique_path(tmp_path / "free.txt") == tmp_path / "free.txt"


def test_apply_renames_processes_children_before_parents(tmp_path):
    folder = tmp_path / "旧"
    folder.mkdir()
    file = folder / "ファイル.txt"
    file.write_text("data")

    result = FilenameTranslateRunner().apply_renames([
        (str(folder), "new_dir"),          # el padre va primero en la lista a propósito
        (str(file), "new_file.txt"),
    ])

    assert result["errors"] == []
    assert [r["old"] for r in result["renamed"]] == [str(file), str(folder)]
    assert (tmp_path / "new_dir" / "new_file.txt").read_text() == "data"


def test_apply_renames_resolves_collisions_and_reports_errors(tmp_path):
    (tmp_path / "taken.txt").write_text("existing")
    src = tmp_path / "src.txt"
    src.write_text("src")

    result = FilenameTranslateRunner().apply_renames([
        (str(src), "taken.txt"),
        (str(tmp_path / "missing.txt"), "whatever.txt"),
    ])

    assert (tmp_path / "taken (2).txt").read_text() == "src"
    assert (tmp_path / "taken.txt").read_text() == "existing"
    assert len(result["renamed"]) == 1
    assert len(result["errors"]) == 1 and result["errors"][0]["path"].endswith("missing.txt")


def test_scan_flags_non_english_names_and_ignores_extension(tmp_path):
    (tmp_path / "こんにちは世界.mp3").write_text("")
    (tmp_path / "hello world.mp3").write_text("")
    sub = tmp_path / "サブフォルダ"
    sub.mkdir()
    (sub / "音声ファイル.wav").write_text("")

    by_name = {r["name"]: r for r in FilenameTranslateRunner().scan(tmp_path)}

    assert by_name["こんにちは世界.mp3"]["needs_translation"] is True
    assert by_name["こんにちは世界.mp3"]["detected_lang"] == "ja"
    assert by_name["hello world.mp3"]["needs_translation"] is False
    assert by_name["サブフォルダ"]["is_dir"] is True and by_name["サブフォルダ"]["needs_translation"] is True
    assert by_name["音声ファイル.wav"]["relative_path"].replace("\\", "/") == "サブフォルダ/音声ファイル.wav"
