"""Translate Chapters: validación de ChaptersOptions."""
import pytest

from core.models import ChaptersOptions
from core.network.remote_target import RemoteTarget


def options(**overrides):
    raw = {"file_paths": ["a.mp4"], "model": "m.gguf"}
    raw.update(overrides)
    return ChaptersOptions.from_dict(raw)


def test_requires_an_object():
    with pytest.raises(ValueError, match="deben ser un objeto"):
        ChaptersOptions.from_dict(["no"])


def test_rejects_unknown_keys():
    with pytest.raises(ValueError, match="Opciones desconocidas: ratonsito"):
        ChaptersOptions.from_dict({"file_paths": ["a"], "model": "m", "ratonsito": 1})


def test_requires_file_paths():
    with pytest.raises(ValueError, match="Faltan opciones: file_paths"):
        ChaptersOptions.from_dict({"model": "m"})


def test_file_paths_must_be_a_non_empty_list_of_strings():
    with pytest.raises(ValueError, match="lista de rutas"):
        options(file_paths="a.mp4")
    with pytest.raises(ValueError, match="al menos un archivo"):
        options(file_paths=[])


def test_requires_a_model():
    with pytest.raises(ValueError, match="Selecciona un modelo"):
        options(model="")


def test_n_gpu_layers_and_n_ctx_default_when_absent():
    opts = options()
    assert opts.n_gpu_layers == 20 and opts.n_ctx == 4096 and opts.temperature == 0.3


def test_optional_text_fields_default_to_empty():
    opts = options()
    assert (opts.raw_publisher_info, opts.base_prompt, opts.glossary) == ("", "", "")


@pytest.mark.parametrize("key", ["raw_publisher_info", "base_prompt", "glossary"])
def test_optional_text_fields_must_be_strings(key):
    with pytest.raises(ValueError, match=f"«{key}» debe ser un texto"):
        options(**{key: 123})


def test_target_absent_or_local_is_none():
    assert options().target is None
    assert options(target={"mode": "local"}).target is None


def test_target_remote_is_a_remote_target():
    t = options(target={"mode": "remote", "host": "1.2.3.4", "port": 9000}).target
    assert isinstance(t, RemoteTarget)
    assert (t.host, t.port) == ("1.2.3.4", 9000)


def test_job_id_is_optional_and_passed_through():
    assert options().job_id is None
    assert options(job_id="abc-123").job_id == "abc-123"


def test_there_is_no_output_subfolder_field():
    # A diferencia de TranslateOptions (SRT): Chapters no crea ningún archivo ni carpeta nueva.
    with pytest.raises(ValueError, match="Opciones desconocidas: output_subfolder"):
        options(output_subfolder="english")
