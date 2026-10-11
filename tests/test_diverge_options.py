"""Validación y resolución de DivergeOptions (opciones que llegan del frontend)."""
from pathlib import Path

import pytest

from core.models import DivergeAudioConfig, DivergeOptions

VALID = {
    "file_path": "C:/audios/show.mp3",
    "base_folder": "C:/Proj",
    "interval_seconds": 1200,
}


def make(**overrides):
    raw = {**VALID, **overrides}
    return {k: v for k, v in raw.items() if v is not ...}  # ... = quitar la clave


# ── from_dict ────────────────────────────────────────────────────────────


def test_minimal_options_get_defaults():
    opts = DivergeOptions.from_dict(VALID)
    assert opts.segment_mode == "interval"
    assert opts.media_type == "audio"
    assert opts.use_subfolder is True
    assert opts.output_folder is None
    assert opts.output_format is None
    assert opts.duration_seconds is None
    assert opts.job_id is None


def test_chapters_mode_takes_null_interval():
    opts = DivergeOptions.from_dict(make(segment_mode="chapters", interval_seconds=None))
    assert opts.segment_mode == "chapters" and opts.interval_seconds is None
    # la clave puede incluso omitirse
    assert DivergeOptions.from_dict(make(segment_mode="chapters", interval_seconds=...)).interval_seconds is None


def test_full_options():
    opts = DivergeOptions.from_dict(make(
        media_type="video", use_subfolder=False, output_folder="C:/out",
        output_format="mp4", duration_seconds=3600.5, job_id="j1",
    ))
    assert (opts.media_type, opts.use_subfolder, opts.output_folder) == ("video", False, "C:/out")
    assert (opts.output_format, opts.duration_seconds, opts.job_id) == ("mp4", 3600.5, "j1")


@pytest.mark.parametrize("raw", [None, [], "texto", 5])
def test_options_must_be_an_object(raw):
    with pytest.raises(ValueError, match="objeto"):
        DivergeOptions.from_dict(raw)


def test_unknown_keys_are_rejected_and_listed():
    with pytest.raises(ValueError, match="desconocidas: foo, zeta"):
        DivergeOptions.from_dict(make(zeta=1, foo=2))


def test_the_old_chapters_option_is_gone():
    # El backend lee los capítulos del archivo; el frontend ya no los envía.
    with pytest.raises(ValueError, match="desconocidas: chapters"):
        DivergeOptions.from_dict(make(chapters=[{"start": 0, "end": 5}]))


def test_missing_keys_are_listed():
    with pytest.raises(ValueError, match="Faltan opciones: file_path, base_folder"):
        DivergeOptions.from_dict(make(file_path=..., base_folder=...))


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"file_path": ""}, "file_path"),
        ({"file_path": 5}, "file_path"),
        ({"base_folder": "   "}, "base_folder"),
        ({"segment_mode": "otro"}, "segment_mode"),
        ({"interval_seconds": ...}, "interval_seconds"),          # obligatorio en modo interval
        ({"interval_seconds": None}, "interval_seconds"),
        ({"interval_seconds": 0}, "interval_seconds"),
        ({"interval_seconds": -5}, "interval_seconds"),
        ({"interval_seconds": "1200"}, "interval_seconds"),
        ({"interval_seconds": True}, "interval_seconds"),
        ({"interval_seconds": float("nan")}, "interval_seconds"),
        ({"segment_mode": "chapters"}, "no se usa en modo"),       # interval_seconds=1200 sobra
        ({"media_type": "image"}, "media_type"),
        ({"use_subfolder": "yes"}, "use_subfolder"),
        ({"output_folder": "C:/out"}, "solo se usa con use_subfolder=false"),
        ({"use_subfolder": False}, "Falta «output_folder»"),
        ({"use_subfolder": False, "output_folder": ""}, "output_folder"),
        ({"output_format": ""}, "output_format"),
        ({"output_format": 3}, "output_format"),
        ({"duration_seconds": 0}, "duration_seconds"),
        ({"duration_seconds": -1}, "duration_seconds"),
        ({"duration_seconds": "x"}, "duration_seconds"),
        ({"job_id": ""}, "job_id"),
        ({"job_id": 7}, "job_id"),
    ],
)
def test_invalid_values_are_rejected_with_a_readable_message(overrides, message):
    with pytest.raises(ValueError, match=message):
        DivergeOptions.from_dict(make(**overrides))


def test_float_interval_is_accepted():
    assert DivergeOptions.from_dict(make(interval_seconds=90.5)).interval_seconds == 90.5


# ── to_config: carpeta de salida efectiva y formato por defecto ───────────


def test_audio_with_subfolder_outputs_under_the_base_folder():
    config = DivergeOptions.from_dict(VALID).to_config()
    assert config == DivergeAudioConfig(
        input_file=Path("C:/audios/show.mp3"),
        base_folder=Path("C:/Proj"),
        output_folder=Path("C:/Proj"),
        interval_seconds=1200,
        output_format="mp3",
        media_type="audio",
        use_subfolder=True,
    )


def test_video_with_subfolder_outputs_next_to_the_file():
    config = DivergeOptions.from_dict(make(
        file_path="C:/videos/clip.mp4", media_type="video",
    )).to_config()
    assert config.output_folder == Path("C:/videos")
    assert config.output_format == "mp4"


def test_without_subfolder_uses_the_chosen_folder():
    config = DivergeOptions.from_dict(make(use_subfolder=False, output_folder="C:/mi/salida")).to_config()
    assert config.output_folder == Path("C:/mi/salida")
    assert config.use_subfolder is False


def test_output_format_defaults_to_the_lowercase_input_extension():
    assert DivergeOptions.from_dict(make(file_path="C:/a/SHOW.MP3")).to_config().output_format == "mp3"


def test_explicit_output_format_is_kept_as_given():
    assert DivergeOptions.from_dict(make(output_format="wav")).to_config().output_format == "wav"


def test_file_without_extension_needs_an_explicit_format():
    opts = DivergeOptions.from_dict(make(file_path="C:/a/show"))
    with pytest.raises(ValueError, match="extensión"):
        opts.to_config()
    assert DivergeOptions.from_dict(make(file_path="C:/a/show", output_format="mp3")).to_config().output_format == "mp3"


def test_chapters_mode_config_has_zero_interval():
    config = DivergeOptions.from_dict(make(segment_mode="chapters", interval_seconds=None)).to_config()
    assert config.interval_seconds == 0
