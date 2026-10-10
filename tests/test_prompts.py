import pytest

from core.translation import prompts


@pytest.fixture
def prompts_dir(tmp_path, monkeypatch):
    root = tmp_path / "prompts"
    for lang, files in {
        "japanese": ["srt_translation.txt", "chapters_translation.txt", "filenames_translation.txt", "glossary.txt"],
        "chinese": ["srt_translation.txt"],
    }.items():
        (root / lang).mkdir(parents=True)
        for f in files:
            (root / lang / f).write_text(f"{lang}:{f}", encoding="utf-8")
    (root / "shared").mkdir()
    (root / "shared" / "work_info_extraction.txt").write_text("extract", encoding="utf-8")
    # carpeta heredada: solo tiene subcarpetas, ningún {kind}_translation.txt
    (root / "old" / "srt" / "presets").mkdir(parents=True)
    (root / "old" / "srt" / "presets" / "japanese.txt").write_text("legacy", encoding="utf-8")
    monkeypatch.setattr(prompts, "_PROMPTS_DIR", root)
    return root


def test_list_languages_excludes_shared_and_legacy_folders(prompts_dir):
    assert prompts.list_languages() == ["chinese", "japanese"]


def test_list_languages_with_missing_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(prompts, "_PROMPTS_DIR", tmp_path / "nope")
    assert prompts.list_languages() == []


def test_new_language_folder_is_discovered_without_code_changes(prompts_dir):
    prompts.save_translation_prompt("korean", "srt", "hola")
    assert "korean" in prompts.list_languages()


def test_get_and_save_roundtrip(prompts_dir):
    assert prompts.get_translation_prompt("japanese", "srt") == "japanese:srt_translation.txt"
    prompts.save_translation_prompt("japanese", "srt", "nuevo")
    assert prompts.get_translation_prompt("japanese", "srt") == "nuevo"
    assert prompts.get_glossary("japanese") == "japanese:glossary.txt"
    assert prompts.get_glossary("chinese") == ""            # no existe: cadena vacía
    assert prompts.get_shared_prompt("work_info_extraction") == "extract"


@pytest.mark.parametrize("language", ["../x", "a/b", "", "shared", "x" * 40])
def test_invalid_language_is_rejected(prompts_dir, language):
    with pytest.raises(ValueError):
        prompts.get_translation_prompt(language, "srt")


def test_invalid_kind_and_shared_name_are_rejected(prompts_dir):
    with pytest.raises(ValueError):
        prompts.get_translation_prompt("japanese", "otro")
    with pytest.raises(ValueError):
        prompts.get_shared_prompt("otro")


# El frontend (TranslateProcessingView.parseSystemPrompt) parsea estos encabezados
# con regex. Hasta que el backend emita secciones estructuradas, cualquier cambio
# de texto aquí rompe esa vista: estos tests lo hacen visible.


def test_build_system_prompt_section_headers_are_stable():
    out = prompts.build_system_prompt("BASE", "gloss", "TITLE", "INFO")
    assert out == (
        "BASE\n"
        "\n[Glossary — use these renderings when the term appears]:\ngloss\n"
        "\n[Work info — persistent context for this work]:\nINFO\n"
        "\n[Translated title]:\nTITLE"
    )


def test_build_system_prompt_omits_empty_sections():
    assert prompts.build_system_prompt("BASE") == "BASE"


def test_build_short_text_prompt_uses_its_own_work_info_header():
    out = prompts.build_short_text_prompt("BASE", "gloss", "INFO")
    assert "[Work info — context for this work]:\nINFO" in out
    assert "[Translated title]" not in out
