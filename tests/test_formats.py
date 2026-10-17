import pytest

from core import formats


def test_defaults_are_the_first_format_of_each_type():
    assert formats.default_output_format("audio") == "mp3"
    assert formats.default_output_format("video") == "mp4"


def test_the_lists_are_the_ones_the_app_always_offered():
    assert formats.output_formats("audio") == ("mp3", "wav", "aac", "m4a", "ogg", "flac", "opus")
    assert formats.output_formats("video") == ("mp4", "mkv", "avi", "mov", "webm")


def test_extensions_match_what_the_folder_scans_have_always_accepted():
    # Estos conjuntos eran literales en api.py; se pinan para que derivarlos no cambie los escaneos.
    assert formats.extensions("audio") == {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}
    assert formats.extensions("video") == {".mp4", ".mkv", ".avi", ".mov", ".webm"}


def test_as_config_is_plain_lists_for_the_frontend():
    cfg = formats.as_config()
    assert cfg == {
        "audio": ["mp3", "wav", "aac", "m4a", "ogg", "flac", "opus"],
        "video": ["mp4", "mkv", "avi", "mov", "webm"],
    }
    assert all(isinstance(v, list) for v in cfg.values())


def test_no_duplicates_and_no_overlap_between_types():
    audio, video = formats.output_formats("audio"), formats.output_formats("video")
    assert len(set(audio)) == len(audio) and len(set(video)) == len(video)
    assert not set(audio) & set(video)


def test_unknown_media_type_is_an_error():
    with pytest.raises(KeyError):
        formats.output_formats("image")
