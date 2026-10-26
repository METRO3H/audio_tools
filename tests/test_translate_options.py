"""Translate (SRT): validación de TranslateOptions."""
import pytest

from core.models import TranslateOptions
from core.network.remote_target import RemoteTarget


def opts_dict(tmp_path, **overrides):
    raw = {"file_paths": [str(tmp_path / "a.srt")], "base_folder": str(tmp_path), "model": "m.gguf"}
    raw.update(overrides)
    return raw


def options(tmp_path, **overrides):
    return TranslateOptions.from_dict(opts_dict(tmp_path, **overrides))


# ── Validación básica ────────────────────────────────────────────────────


def test_requires_an_object():
    with pytest.raises(ValueError, match="deben ser un objeto"):
        TranslateOptions.from_dict(["no", "un", "dict"])


def test_rejects_unknown_keys():
    with pytest.raises(ValueError, match="Opciones desconocidas: ratonsito"):
        TranslateOptions.from_dict({"file_paths": ["x"], "base_folder": "/x", "model": "m", "ratonsito": 1})


def test_requires_file_paths_and_base_folder():
    with pytest.raises(ValueError, match="Faltan opciones: file_paths, base_folder"):
        TranslateOptions.from_dict({"model": "m"})


def test_file_paths_must_be_a_non_empty_list_of_strings(tmp_path):
    with pytest.raises(ValueError, match="lista de rutas"):
        options(tmp_path, file_paths="a.srt")
    with pytest.raises(ValueError, match="lista de rutas"):
        options(tmp_path, file_paths=[""])
    with pytest.raises(ValueError, match="al menos un .srt"):
        options(tmp_path, file_paths=[])


def test_requires_a_model():
    with pytest.raises(ValueError, match="Selecciona un modelo"):
        TranslateOptions.from_dict({"file_paths": ["a.srt"], "base_folder": "/x", "model": ""})
    with pytest.raises(ValueError, match="Selecciona un modelo"):
        TranslateOptions.from_dict({"file_paths": ["a.srt"], "base_folder": "/x"})


def test_model_is_stripped(tmp_path):
    assert options(tmp_path, model="  m.gguf  ").model == "m.gguf"


# ── output_subfolder ─────────────────────────────────────────────────────


def test_output_subfolder_defaults_to_english(tmp_path):
    assert options(tmp_path).output_subfolder == "english"
    assert options(tmp_path, output_subfolder="").output_subfolder == "english"
    assert options(tmp_path, output_subfolder=None).output_subfolder == "english"


@pytest.mark.parametrize("bad", ["../evil", "a/b", "a\\b", "C:evil", ".", ".."])
def test_output_subfolder_rejects_paths_and_separators(tmp_path, bad):
    with pytest.raises(ValueError, match="un solo nombre de carpeta"):
        options(tmp_path, output_subfolder=bad)


def test_output_subfolder_is_sanitized_like_windows_requires(tmp_path):
    # sanitize_name sustituye caracteres no admitidos; además se recorta el punto/espacio final.
    assert options(tmp_path, output_subfolder="mi serie. ").output_subfolder == "mi serie"


# ── números ───────────────────────────────────────────────────────────────


def test_n_gpu_layers_and_n_ctx_default_when_absent(tmp_path):
    opts = options(tmp_path)
    assert opts.n_gpu_layers == 20 and opts.n_ctx == 4096


def test_n_gpu_layers_must_be_a_whole_number(tmp_path):
    with pytest.raises(ValueError):
        options(tmp_path, n_gpu_layers=1.5)
    with pytest.raises(ValueError):
        options(tmp_path, n_gpu_layers="20")


def test_temperature_must_be_a_number(tmp_path):
    with pytest.raises(ValueError, match="«temperature» debe ser un número"):
        options(tmp_path, temperature="alta")
    assert options(tmp_path, temperature=1).temperature == 1.0


# ── textos opcionales ────────────────────────────────────────────────────


@pytest.mark.parametrize("key", ["raw_title", "raw_publisher_info", "base_prompt", "glossary", "source_language"])
def test_optional_text_fields_must_be_strings(tmp_path, key):
    with pytest.raises(ValueError, match=f"«{key}» debe ser un texto"):
        options(tmp_path, **{key: 123})


def test_optional_text_fields_default_to_empty(tmp_path):
    opts = options(tmp_path)
    assert (opts.raw_title, opts.raw_publisher_info, opts.base_prompt, opts.glossary, opts.source_language) == (
        "", "", "", "", "",
    )


# ── target ────────────────────────────────────────────────────────────────


def test_target_absent_or_local_is_none(tmp_path):
    assert options(tmp_path).target is None
    assert options(tmp_path, target={"mode": "local"}).target is None


def test_target_remote_is_a_remote_target(tmp_path):
    t = options(tmp_path, target={"mode": "remote", "host": "1.2.3.4", "port": 9000}).target
    assert isinstance(t, RemoteTarget)
    assert (t.host, t.port) == ("1.2.3.4", 9000)


# ── job_id ───────────────────────────────────────────────────────────────


def test_job_id_is_optional_and_passed_through(tmp_path):
    assert options(tmp_path).job_id is None
    assert options(tmp_path, job_id="abc-123").job_id == "abc-123"


def test_invalid_job_id_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="«job_id» no es válida"):
        options(tmp_path, job_id=123)
