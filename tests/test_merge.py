"""Merge: opciones, resolución de duraciones, plan, comando y paso final."""
import os
from pathlib import Path

import pytest

from core.actions import merge_audio
from core.actions.merge_audio import MergeAudioAction, resolve_merge
from core.models import MergeAudioConfig, MergeOptions


def opts_dict(tmp_path, **overrides):
    raw = {
        "file_paths": [str(tmp_path / "a.mp3"), str(tmp_path / "b.mp3")],
        "output_name": "Proj",
        "output_format": "mp3",
    }
    raw.update(overrides)
    return {k: v for k, v in raw.items() if v is not ...}  # ... = quitar la clave


def options(tmp_path, **overrides):
    return MergeOptions.from_dict(opts_dict(tmp_path, **overrides))


# ── MergeOptions ─────────────────────────────────────────────────────────


def test_minimal_options_get_defaults(tmp_path):
    opts = options(tmp_path)
    assert (opts.media_type, opts.durations, opts.job_id) == ("audio", None, None)


def test_the_output_goes_next_to_the_first_file(tmp_path):
    folder = tmp_path / "audios"
    opts = options(tmp_path, file_paths=[str(folder / "a.mp3"), str(tmp_path / "otra" / "b.mp3")])
    cfg = opts.to_config()
    assert cfg.output_file == folder / "Proj.mp3"
    assert cfg.input_files == [folder / "a.mp3", tmp_path / "otra" / "b.mp3"]


def test_output_name_is_cleaned_for_windows(tmp_path):
    assert options(tmp_path, output_name="Parte 1: Intro").output_name == "Parte 1 - Intro"
    assert options(tmp_path, output_name="AC/DC").output_name == "AC-DC"


def test_output_format_is_case_insensitive(tmp_path):
    assert options(tmp_path, output_format="MP3").output_format == "mp3"


def test_video_formats_are_validated_against_video(tmp_path):
    assert options(tmp_path, media_type="video", output_format="mkv").output_format == "mkv"
    with pytest.raises(ValueError, match="«mp3» no es válido para video"):
        options(tmp_path, media_type="video", output_format="mp3")


@pytest.mark.parametrize("raw", [None, [], "texto", 5])
def test_options_must_be_an_object(raw):
    with pytest.raises(ValueError, match="objeto"):
        MergeOptions.from_dict(raw)


def test_unknown_keys_are_rejected_including_the_old_positional_ones(tmp_path):
    with pytest.raises(ValueError, match="desconocidas: base_folder, output_path"):
        options(tmp_path, base_folder="C:/Proj", output_path="C:/x.mp3")


def test_missing_keys_are_listed(tmp_path):
    with pytest.raises(ValueError, match="Faltan opciones: file_paths, output_format"):
        options(tmp_path, file_paths=..., output_format=...)


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"file_paths": "a.mp3"}, "file_paths"),
        ({"file_paths": ["a.mp3", ""]}, "file_paths"),
        ({"file_paths": ["a.mp3", 5]}, "file_paths"),
        ({"file_paths": ["solo.mp3"]}, "al menos 2 archivos"),
        ({"file_paths": []}, "al menos 2 archivos"),
        ({"media_type": "image"}, "media_type"),
        ({"output_name": ""}, "output_name"),
        ({"output_name": 5}, "output_name"),
        ({"output_name": "???"}, "nombre de salida no es válido"),
        ({"output_format": ""}, "output_format"),
        ({"output_format": "xyz"}, "«xyz» no es válido para audio"),
        ({"durations": [1.0]}, "una duración por archivo"),
        ({"durations": "10"}, "una duración por archivo"),
        ({"durations": [1.0, -2]}, "mayor o igual que 0"),
        ({"durations": [1.0, "x"]}, "mayor o igual que 0"),
        ({"durations": [1.0, float("nan")]}, "mayor o igual que 0"),
        ({"job_id": ""}, "job_id"),
        ({"job_id": 7}, "job_id"),
    ],
)
def test_invalid_values_are_rejected_with_a_readable_message(tmp_path, overrides, message):
    with pytest.raises(ValueError, match=message):
        options(tmp_path, **overrides)


def test_unknown_durations_may_be_null_or_zero(tmp_path):
    assert options(tmp_path, durations=[None, 0]).durations == [None, 0]


def test_the_error_for_an_unsupported_format_lists_the_valid_ones(tmp_path):
    with pytest.raises(ValueError, match="mp3, wav, aac, m4a, ogg, flac, opus"):
        options(tmp_path, output_format="xyz")


# ── resolve_merge ────────────────────────────────────────────────────────


class Probe:
    def __init__(self, values=None, error=None):
        self.values, self.error, self.calls = values or {}, error, []

    def __call__(self, path):
        self.calls.append(path.name)
        if self.error:
            raise self.error
        return self.values.get(path.name, 42.0)


def test_known_durations_are_used_without_probing(tmp_path):
    probe = Probe()
    inputs = resolve_merge(options(tmp_path, durations=[10.5, 5]), probe)
    assert inputs.durations == [10.5, 5.0]
    assert all(isinstance(d, float) for d in inputs.durations)
    assert probe.calls == []


def test_only_missing_or_zero_durations_are_probed(tmp_path):
    probe = Probe({"b.mp3": 7.0})
    names = ["a.mp3", "b.mp3", "c.mp3", "d.mp3"]
    opts = options(tmp_path, file_paths=[str(tmp_path / n) for n in names], durations=[10, None, 5, 0])
    inputs = resolve_merge(opts, probe)
    assert inputs.durations == [10.0, 7.0, 5.0, 42.0]
    assert probe.calls == ["b.mp3", "d.mp3"]


def test_without_any_durations_all_are_probed(tmp_path):
    probe = Probe({"a.mp3": 3.0, "b.mp3": 4.0})
    assert resolve_merge(options(tmp_path), probe).durations == [3.0, 4.0]
    assert probe.calls == ["a.mp3", "b.mp3"]


def test_an_unreadable_file_gives_a_readable_error_naming_it(tmp_path):
    probe = Probe(error=ValueError("could not convert string to float: ''"))
    with pytest.raises(ValueError, match="No se pudo leer la duración de «a.mp3»"):
        resolve_merge(options(tmp_path), probe)


# ── plan ─────────────────────────────────────────────────────────────────


def plan_for(tmp_path, names, durations, out="Proj.mp3"):
    cfg = MergeAudioConfig(input_files=[tmp_path / "audios" / n for n in names], output_file=tmp_path / "audios" / out)
    return MergeAudioAction().plan(cfg, durations)


def test_plan_lays_out_each_file_after_the_previous_one(tmp_path):
    plan = plan_for(tmp_path, ["a.mp3", "b.mp3", "c.mp3"], [10.5, 5.0, 2.0])
    assert [(f.index, f.name, f.start, f.end) for f in plan.files] == [
        (1, "a.mp3", 0.0, 10.5), (2, "b.mp3", 10.5, 15.5), (3, "c.mp3", 15.5, 17.5),
    ]
    assert plan.total_duration == 17.5
    assert plan.excluded == []
    assert plan.chapters == [
        {"index": 1, "title": "a", "start": 0.0, "end": 10.5},
        {"index": 2, "title": "b", "start": 10.5, "end": 15.5},
        {"index": 3, "title": "c", "start": 15.5, "end": 17.5},
    ]


def test_plan_to_dict_shape(tmp_path):
    d = plan_for(tmp_path, ["a.mp3", "b.mp3"], [10.0, 5.0]).to_dict()
    folder = tmp_path / "audios"
    assert d == {
        "output_path": str(folder / "Proj.mp3"),
        "output_name": "Proj.mp3",
        "files": [
            {"index": 1, "name": "a.mp3", "path": str(folder / "a.mp3"), "duration": 10.0, "start": 0.0, "end": 10.0},
            {"index": 2, "name": "b.mp3", "path": str(folder / "b.mp3"), "duration": 5.0, "start": 10.0, "end": 15.0},
        ],
        "excluded": [],
        "total_duration": 15.0,
        "chapters": [
            {"index": 1, "title": "a", "start": 0.0, "end": 10.0},
            {"index": 2, "title": "b", "start": 10.0, "end": 15.0},
        ],
    }


# El defecto real: si entre las entradas está el merge anterior, ffmpeg lo excluía pero los
# capítulos y el progreso seguían usando la lista completa (3 capítulos y 115 s para un audio de 15 s).


def test_regression_previous_merge_as_last_input_is_dropped_with_its_duration(tmp_path):
    plan = plan_for(tmp_path, ["a.mp3", "b.mp3", "Proj.mp3"], [10.0, 5.0, 100.0])
    assert [f.name for f in plan.files] == ["a.mp3", "b.mp3"]
    assert plan.total_duration == 15.0
    assert [(c["title"], c["start"], c["end"]) for c in plan.chapters] == [("a", 0.0, 10.0), ("b", 10.0, 15.0)]
    assert [p.name for p in plan.excluded] == ["Proj.mp3"]


@pytest.mark.parametrize(
    "names, durations",
    [
        (["Proj.mp3", "a.mp3", "b.mp3"], [100.0, 10.0, 5.0]),   # al principio
        (["a.mp3", "Proj.mp3", "b.mp3"], [10.0, 100.0, 5.0]),   # en medio
    ],
)
def test_regression_durations_stay_aligned_wherever_the_previous_merge_is(tmp_path, names, durations):
    plan = plan_for(tmp_path, names, durations)
    assert [(f.name, f.duration, f.start) for f in plan.files] == [("a.mp3", 10.0, 0.0), ("b.mp3", 5.0, 10.0)]
    assert plan.total_duration == 15.0


def test_the_output_is_recognised_even_through_different_spellings_of_its_path(tmp_path):
    (tmp_path / "audios").mkdir()
    cfg = MergeAudioConfig(
        input_files=[tmp_path / "audios" / "a.mp3", tmp_path / "audios" / "b.mp3",
                     tmp_path / "audios" / ".." / "audios" / "Proj.mp3"],
        output_file=tmp_path / "audios" / "Proj.mp3",
    )
    plan = MergeAudioAction().plan(cfg, [1.0, 2.0, 99.0])
    assert [f.name for f in plan.files] == ["a.mp3", "b.mp3"]
    assert len(plan.excluded) == 1


@pytest.mark.parametrize("names", [["a.mp3", "Proj.mp3"], ["Proj.mp3", "Proj.mp3"], ["a.mp3"]])
def test_fewer_than_two_effective_files_is_an_error(tmp_path, names):
    with pytest.raises(ValueError, match="al menos 2 archivos"):
        plan_for(tmp_path, names, [1.0] * len(names))


def test_planning_has_no_side_effects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plan_for(tmp_path, ["a.mp3", "b.mp3"], [1.0, 2.0])
    assert sorted(os.listdir(tmp_path)) == []


# ── build_command ────────────────────────────────────────────────────────


def test_command_arguments_are_the_ones_the_merge_has_always_used(tmp_path):
    plan = plan_for(tmp_path, ["a.mp3", "b.mp3"], [10.0, 5.0])
    work = tmp_path / "work"
    work.mkdir()
    cmd = MergeAudioAction().build_command(plan, work)
    assert cmd.args == ["-y", "-f", "concat", "-safe", "0", "-i", str(work / "concat_list.txt"), str(plan.output_path)]
    assert cmd.duration == 15.0
    assert cmd.output == plan.output_path
    assert cmd.label == "Proj.mp3"


def test_concat_list_has_only_the_effective_files_in_order(tmp_path):
    plan = plan_for(tmp_path, ["a.mp3", "Proj.mp3", "b.mp3"], [1.0, 99.0, 2.0])
    work = tmp_path / "work"
    work.mkdir()
    MergeAudioAction().build_command(plan, work)
    lines = (work / "concat_list.txt").read_text(encoding="utf-8").splitlines()
    assert lines == [f"file '{(tmp_path / 'audios' / n).as_posix()}'" for n in ("a.mp3", "b.mp3")]


def test_concat_list_escapes_single_quotes(tmp_path):
    plan = plan_for(tmp_path, ["it's.mp3", "b.mp3"], [1.0, 2.0])
    work = tmp_path / "work"
    work.mkdir()
    MergeAudioAction().build_command(plan, work)
    first = (work / "concat_list.txt").read_text(encoding="utf-8").splitlines()[0]
    assert first == f"file '{(tmp_path / 'audios' / 'it').as_posix()}'\\''s.mp3'"


def test_building_the_command_leaves_nothing_in_the_working_directory(tmp_path, monkeypatch):
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    plan = plan_for(tmp_path, ["a.mp3", "b.mp3"], [1.0, 2.0])
    work = tmp_path / "work"
    work.mkdir()
    MergeAudioAction().build_command(plan, work)
    assert os.listdir(elsewhere) == []  # antes escribía _concat_list.txt en el CWD


# ── finalize ─────────────────────────────────────────────────────────────


@pytest.fixture
def embed_calls(monkeypatch):
    calls = []

    def fake_embed(ffmpeg_bin, media_file, chapters, workdir):
        calls.append((ffmpeg_bin, media_file, chapters, workdir))
        return fake_embed.result

    fake_embed.result = None
    monkeypatch.setattr(merge_audio, "embed_chapters", fake_embed)
    return calls, fake_embed


def finalize_setup(tmp_path):
    plan = plan_for(tmp_path, ["a.mp3", "b.mp3"], [10.0, 5.0])
    plan.output_path.parent.mkdir(parents=True, exist_ok=True)
    work = tmp_path / "work"
    work.mkdir()
    (work / "concat_list.txt").write_text("x")
    return plan, work


def test_success_embeds_the_chapters_of_the_effective_list_and_cleans_up(tmp_path, embed_calls):
    calls, _ = embed_calls
    plan, work = finalize_setup(tmp_path)
    plan.output_path.write_bytes(b"merged")

    assert MergeAudioAction().finalize(plan, True, "ffmpeg", work) is None
    assert calls == [("ffmpeg", plan.output_path, plan.chapters, work)]
    assert plan.output_path.exists()
    assert not work.exists()


def test_a_chapter_failure_is_a_warning_not_a_failure(tmp_path, embed_calls):
    _, fake = embed_calls
    fake.result = "Error: sin permiso"
    plan, work = finalize_setup(tmp_path)
    plan.output_path.write_bytes(b"merged")

    warning = MergeAudioAction().finalize(plan, True, "ffmpeg", work)
    assert warning == "No se pudieron incrustar los capítulos: Error: sin permiso"
    assert plan.output_path.exists()   # el audio unido se conserva
    assert not work.exists()


def test_if_embedding_cannot_run_the_error_propagates_but_the_workdir_is_still_removed(tmp_path, monkeypatch):
    def boom(*args):
        raise FileNotFoundError("ffmpeg no encontrado")

    monkeypatch.setattr(merge_audio, "embed_chapters", boom)
    plan, work = finalize_setup(tmp_path)
    with pytest.raises(FileNotFoundError):
        MergeAudioAction().finalize(plan, True, "ffmpeg", work)
    assert not work.exists()


@pytest.mark.parametrize("had_output", [True, False])
def test_failure_or_cancellation_deletes_the_partial_output_and_cleans_up(tmp_path, embed_calls, had_output):
    calls, _ = embed_calls
    plan, work = finalize_setup(tmp_path)
    if had_output:
        plan.output_path.write_bytes(b"incompleto")

    assert MergeAudioAction().finalize(plan, False, "ffmpeg", work) is None
    assert not plan.output_path.exists()
    assert not work.exists()
    assert calls == []   # sin capítulos si el merge no terminó


# ── finalize: la salida debe durar lo esperado ───────────────────────────
# ffmpeg termina con código 0 aunque no pueda leer un archivo y produce una salida truncada.


def run_finalize(tmp_path, actual, embed_result=None, monkeypatch=None, **kw):
    plan, work = finalize_setup(tmp_path)
    plan.output_path.write_bytes(b"merged")
    probe = actual if callable(actual) else (lambda path: actual)
    return MergeAudioAction().finalize(plan, True, "ffmpeg", work, probe_duration=probe), plan


@pytest.mark.parametrize("actual", [15.0, 14.5, 13.9, 16.5])  # expected 15 s, 2 archivos: tolerancia 1.2 s
def test_a_duration_close_to_the_expected_one_gives_no_warning(tmp_path, embed_calls, actual):
    warning, _ = run_finalize(tmp_path, actual)
    assert warning is None


def test_a_truncated_output_gives_a_warning_naming_both_durations(tmp_path, embed_calls):
    warning, plan = run_finalize(tmp_path, 10.0)   # faltan 5 s
    assert warning == (
        "El archivo resultante dura 0:10 y se esperaban 0:15: "
        "es posible que falte audio (¿algún archivo de entrada está dañado o no se pudo leer?)."
    )
    assert plan.output_path.exists()                # el resultado se conserva


def test_the_tolerance_grows_with_the_number_of_files(tmp_path, embed_calls):
    plan = plan_for(tmp_path, [f"{i}.mp3" for i in range(10)], [60.0] * 10)   # 600 s, tolerancia 2 s
    plan.output_path.parent.mkdir(parents=True, exist_ok=True)
    plan.output_path.write_bytes(b"x")
    action = MergeAudioAction()
    for actual, expect_warning in [(598.5, False), (597.0, True)]:
        work = tmp_path / f"work{actual}"
        work.mkdir()
        warning = action.finalize(plan, True, "ffmpeg", work, probe_duration=lambda p, a=actual: a)
        assert (warning is not None) is expect_warning, actual


def test_if_the_output_cannot_be_measured_that_is_a_warning(tmp_path, embed_calls):
    def broken(path):
        raise ValueError("no legible")

    warning, _ = run_finalize(tmp_path, broken)
    assert warning == "No se pudo verificar la duración del archivo resultante."


def test_duration_and_chapter_warnings_are_combined(tmp_path, embed_calls):
    _, fake = embed_calls
    fake.result = "Error: sin permiso"
    warning, _ = run_finalize(tmp_path, 10.0)
    assert "es posible que falte audio" in warning
    assert warning.endswith("No se pudieron incrustar los capítulos: Error: sin permiso")


def test_without_a_probe_the_duration_is_not_checked(tmp_path, embed_calls):
    plan, work = finalize_setup(tmp_path)
    plan.output_path.write_bytes(b"merged")
    assert MergeAudioAction().finalize(plan, True, "ffmpeg", work) is None


def test_failure_never_probes_the_duration(tmp_path, embed_calls):
    plan, work = finalize_setup(tmp_path)

    def must_not_run(path):
        raise AssertionError("no debe medirse la salida de un job fallido")

    assert MergeAudioAction().finalize(plan, False, "ffmpeg", work, probe_duration=must_not_run) is None
