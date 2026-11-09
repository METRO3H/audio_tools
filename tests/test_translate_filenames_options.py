"""Translate Filenames: validación de FilenamesOptions."""
import pytest

from core.models import FilenamesOptions
from core.network.remote_target import RemoteTarget

SCANNED = [{"path": "/a", "relative_path": "a", "name": "a", "is_dir": False,
            "detected_lang": "ja", "needs_translation": True}]


def options(**overrides):
    raw = {"files": SCANNED, "model": "m.gguf"}
    raw.update(overrides)
    return FilenamesOptions.from_dict(raw)


def test_requires_an_object():
    with pytest.raises(ValueError, match="deben ser un objeto"):
        FilenamesOptions.from_dict(["no"])


def test_rejects_unknown_keys():
    with pytest.raises(ValueError, match="Opciones desconocidas: ratonsito"):
        FilenamesOptions.from_dict({"files": SCANNED, "model": "m", "ratonsito": 1})


def test_requires_files():
    with pytest.raises(ValueError, match="Faltan opciones: files"):
        FilenamesOptions.from_dict({"model": "m"})


def test_files_must_be_a_list_of_dicts_with_path():
    with pytest.raises(ValueError, match="resultados de scan_filenames_folder"):
        options(files="no")
    with pytest.raises(ValueError, match="resultados de scan_filenames_folder"):
        options(files=[{"no_path": 1}])


def test_files_cannot_be_empty():
    with pytest.raises(ValueError, match="escaneá una carpeta primero"):
        options(files=[])


def test_requires_a_model():
    with pytest.raises(ValueError, match="Selecciona un modelo"):
        options(model="")


def test_n_gpu_layers_and_n_ctx_default_when_absent():
    opts = options()
    assert opts.n_gpu_layers == 20 and opts.n_ctx == 4096 and opts.temperature == 0.3


def test_optional_text_fields_default_to_empty():
    opts = options()
    assert (opts.raw_publisher_info, opts.base_prompt, opts.glossary) == ("", "", "")


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
