"""Transcribe: capacidades, destino (local/remoto), subcarpeta y TranscribeOptions."""
import pytest

from core.models import TranscribeOptions
from core.network.remote_target import RemoteTarget, parse_target
from core.transcription import options as whisper_options


def opts_dict(tmp_path, **overrides):
    raw = {"file_paths": [str(tmp_path / "ep1.mp3")], "base_folder": str(tmp_path)}
    raw.update(overrides)
    return raw


def options(tmp_path, **overrides):
    return TranscribeOptions.from_dict(opts_dict(tmp_path, **overrides))


# ── Capacidades ──────────────────────────────────────────────────────────


def test_languages_are_shown_with_their_full_name_never_abbreviated():
    cfg = whisper_options.as_config()
    assert cfg["languages"] == [{"code": "ja", "label": "japanese"}, {"code": "zh", "label": "chinese"}]


def test_capabilities_shape_for_the_frontend():
    cfg = whisper_options.as_config("mi prompt")
    assert cfg["model_sizes"] == ["tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3"]
    assert cfg["devices"] == ["cuda", "cpu"]
    assert cfg["compute_types"] == {"cuda": ["float16", "int8_float16", "int8"], "cpu": ["float32", "int8"]}
    assert cfg["beam_sizes"] == list(range(1, 11))
    assert cfg["output_formats"] == ["srt", "vtt", "txt"]
    assert cfg["defaults"] == {
        "model_size": "large-v3", "device": "cuda", "compute_type": "int8_float16", "beam_size": 5,
        "language": "ja", "vad_filter": True, "condition_on_previous_text": False,
        "word_timestamps": True, "output_format": "srt", "initial_prompt": "mi prompt",
    }


def test_every_default_is_one_of_the_offered_values():
    d = whisper_options.DEFAULTS
    assert d["model_size"] in whisper_options.MODEL_SIZES
    assert d["device"] in whisper_options.DEVICES
    assert d["compute_type"] in whisper_options.COMPUTE_TYPES[d["device"]]
    assert d["beam_size"] in whisper_options.BEAM_SIZES
    assert d["language"] in whisper_options.LANGUAGES
    assert d["output_format"] in whisper_options.OUTPUT_FORMATS


# ── Destino ──────────────────────────────────────────────────────────────


def test_local_target_is_none():
    assert parse_target(None) is None
    assert parse_target({"mode": "local"}) is None


def test_remote_target():
    assert parse_target({"mode": "remote", "host": " 192.168.1.20 ", "port": 8765}) == RemoteTarget("192.168.1.20", 8765)
    assert parse_target({"mode": "remote", "host": "h", "port": 80.0}) == RemoteTarget("h", 80)
    assert str(RemoteTarget("h", 80)) == "h:80"


@pytest.mark.parametrize(
    "raw, message",
    [
        ("remote", "objeto"),
        ({"mode": "x"}, "local.*remote"),
        ({}, "local.*remote"),
        ({"mode": "local", "host": "h"}, "no lleva host ni puerto"),
        ({"mode": "local", "port": 1}, "no lleva host ni puerto"),
        ({"mode": "remote", "port": 80}, "host"),
        ({"mode": "remote", "host": "", "port": 80}, "host"),
        ({"mode": "remote", "host": "h"}, "port"),
        ({"mode": "remote", "host": "h", "port": 0}, "port"),
        ({"mode": "remote", "host": "h", "port": 70000}, "port"),
        ({"mode": "remote", "host": "h", "port": 8.5}, "port"),
        ({"mode": "remote", "host": "h", "port": True}, "port"),
        ({"mode": "remote", "host": "h", "port": "80"}, "port"),
        ({"mode": "remote", "host": "h", "port": 80, "extra": 1}, "desconocidas: extra"),
    ],
)
def test_invalid_targets_are_rejected_readably(raw, message):
    with pytest.raises(ValueError, match=message):
        parse_target(raw)


# ── Subcarpeta ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw, language, expected", [
    (None, "ja", "japanese"), ("", "zh", "chinese"), ("   ", "ja", "japanese"),
    ("Mi serie", "ja", "Mi serie"), ("  temporada 1  ", "zh", "temporada 1"),
    ("Parte: 1", "ja", "Parte - 1"), ("a?b*c", "ja", "abc"), ("nombre.", "ja", "nombre"),
])
def test_the_subfolder_defaults_to_the_language_and_is_cleaned(raw, language, expected):
    assert whisper_options.resolve_subfolder(raw, language) == expected


@pytest.mark.parametrize("raw", ["../../escapado", "..", ".", "a/b", "a\\b", "C:\\Windows", "c:x", "/etc", "..\\x"])
def test_a_subfolder_with_a_path_is_rejected(raw):
    """Antes `../../escapado` creaba la carpeta y escribía fuera de <base>/transcriptions."""
    with pytest.raises(ValueError, match="un solo nombre de carpeta"):
        whisper_options.resolve_subfolder(raw, "ja")


def test_a_subfolder_with_nothing_usable_is_rejected():
    with pytest.raises(ValueError, match="no es un nombre válido"):
        whisper_options.resolve_subfolder("???", "ja")
    with pytest.raises(ValueError, match="no es un nombre válido"):
        whisper_options.resolve_subfolder("...", "ja")


# ── TranscribeOptions ────────────────────────────────────────────────────


def test_minimal_options_get_the_backend_defaults(tmp_path):
    o = options(tmp_path)
    assert (o.model_size, o.device, o.compute_type, o.beam_size, o.language) == ("large-v3", "cuda", "int8_float16", 5, "ja")
    assert (o.vad_filter, o.condition_on_previous_text, o.word_timestamps) == (True, False, True)
    assert (o.initial_prompt, o.output_format, o.output_subfolder, o.target) == ("", "srt", "japanese", None)
    assert (o.durations, o.job_id) == (None, None)


def test_the_subfolder_follows_the_language_when_not_given(tmp_path):
    assert options(tmp_path, language="zh").output_subfolder == "chinese"
    assert options(tmp_path, language="zh", output_subfolder="mi carpeta").output_subfolder == "mi carpeta"


def test_options_must_be_an_object():
    with pytest.raises(ValueError, match="objeto"):
        TranscribeOptions.from_dict([])


def test_unknown_and_missing_keys_are_listed(tmp_path):
    with pytest.raises(ValueError, match="Opciones desconocidas: remote_host, remote_port"):
        options(tmp_path, remote_host="h", remote_port=1)
    with pytest.raises(ValueError, match="Faltan opciones: file_paths, base_folder"):
        TranscribeOptions.from_dict({})


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"file_paths": []}, "al menos un audio"),
        ({"file_paths": "a.mp3"}, "file_paths"),
        ({"file_paths": [""]}, "file_paths"),
        ({"base_folder": ""}, "base_folder"),
        ({"model_size": "gigante"}, "model_size"),
        ({"device": "tpu"}, "device"),
        ({"compute_type": "float32"}, "compute_type.*cuda"),
        ({"device": "cpu", "compute_type": "float16"}, "compute_type.*cpu"),
        ({"beam_size": 0}, "beam_size"),
        ({"beam_size": 11}, "beam_size"),
        ({"beam_size": 2.5}, "beam_size"),
        ({"beam_size": True}, "beam_size"),
        ({"language": "japanese"}, "language"),
        ({"language": "auto"}, "language"),
        ({"output_format": "xyz"}, "output_format"),
        ({"vad_filter": 1}, "vad_filter"),
        ({"condition_on_previous_text": "no"}, "condition_on_previous_text"),
        ({"word_timestamps": None}, "word_timestamps"),
        ({"initial_prompt": 5}, "initial_prompt"),
        ({"output_subfolder": 5}, "output_subfolder"),
        ({"output_subfolder": "../x"}, "un solo nombre de carpeta"),
        ({"target": {"mode": "remote"}}, "host"),
        ({"durations": [1, 2]}, "durations"),
        ({"durations": [-1]}, "durations"),
        ({"job_id": ""}, "job_id"),
    ],
)
def test_invalid_values_are_rejected_with_a_readable_message(tmp_path, overrides, message):
    with pytest.raises(ValueError, match=message):
        options(tmp_path, **overrides)


def test_the_compute_type_is_checked_against_the_device(tmp_path):
    assert options(tmp_path, device="cpu", compute_type="float32").compute_type == "float32"
    assert options(tmp_path, device="cuda", compute_type="float16").compute_type == "float16"


def test_a_remote_target_accepts_any_model_name_because_the_list_is_the_mediators(tmp_path):
    target = {"mode": "remote", "host": "10.0.0.5", "port": 9000}
    o = options(tmp_path, model_size=" modelo-del-mediador ", target=target)
    assert o.model_size == "modelo-del-mediador" and o.target == RemoteTarget("10.0.0.5", 9000)
    with pytest.raises(ValueError, match="nombre de un modelo"):
        options(tmp_path, model_size="", target=target)


def test_whole_numbers_sent_as_floats_are_accepted(tmp_path):
    o = options(tmp_path, beam_size=4.0)
    assert o.beam_size == 4 and isinstance(o.beam_size, int)


def test_to_configs_gives_one_config_per_file_with_its_duration(tmp_path):
    o = options(tmp_path, file_paths=[str(tmp_path / "a.mp3"), str(tmp_path / "b.wav")],
                language="zh", output_format="vtt", initial_prompt="hola", beam_size=3)
    a, b = o.to_configs([10.0, 20.0])
    assert (a.input_file, b.input_file) == (tmp_path / "a.mp3", tmp_path / "b.wav")
    assert (a.total_duration, b.total_duration) == (10.0, 20.0)
    assert (a.base_folder, a.output_subfolder, a.output_format) == (tmp_path, "chinese", "vtt")
    assert (a.language, a.beam_size, a.initial_prompt, a.model_size) == ("zh", 3, "hola", "large-v3")
