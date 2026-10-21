"""Audio→Video: opciones, capacidades, resolución, plan y comandos (sin lanzar ffmpeg)."""
import subprocess

import pytest

from core import video_encoding
from core.actions.audio_to_video import AudioToVideoAction, resolve_audio_to_video
from core.models import AudioToVideoConfig, AudioToVideoOptions


def make_files(tmp_path, *names):
    """Crea los audios en disco (la resolución comprueba que existan) y devuelve sus rutas."""
    paths = []
    for name in names:
        path = tmp_path / "audios" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"x")
        paths.append(path)
    return paths


def opts_dict(tmp_path, **overrides):
    raw = {
        "file_paths": [str(tmp_path / "audios" / "ep1.mp3")],
        "base_folder": str(tmp_path),
    }
    raw.update(overrides)
    return {k: v for k, v in raw.items() if v is not ...}  # ... = quitar la clave


def options(tmp_path, **overrides):
    return AudioToVideoOptions.from_dict(opts_dict(tmp_path, **overrides))


# ── Capacidades ──────────────────────────────────────────────────────────


def test_every_encoder_has_a_label_a_preset_list_and_a_default_inside_it():
    for key in video_encoding.ENCODERS:
        assert key in video_encoding.ENCODER_LABELS
        assert video_encoding.DEFAULT_PRESETS[key] in video_encoding.PRESETS[key]
    assert sorted(video_encoding.ENCODER_PRIORITY) == sorted(video_encoding.ENCODERS)


def test_the_priority_puts_the_cpu_last_as_the_universal_fallback():
    assert video_encoding.ENCODER_PRIORITY[-1] == "cpu"
    assert video_encoding.ENCODER_PRIORITY[0] == "nvidia"


def test_capabilities_shape_for_the_frontend():
    cfg = video_encoding.as_config()
    assert [e["id"] for e in cfg["encoders"]] == ["cpu", "nvidia", "amd", "intel"]
    assert cfg["presets"]["nvidia"] == ["p1", "p2", "p3", "p4", "p5", "p6", "p7"]
    assert cfg["default_presets"] == {"cpu": "medium", "nvidia": "p4", "amd": "medium", "intel": "medium"}
    assert cfg["fps"] == [1, 24, 30, 60]
    assert cfg["resolutions"] == ["1280x720", "1920x1080", "3840x2160"]
    assert cfg["quality_range"] == [0, 51]


class FakeRun:
    """Sustituye a subprocess.run: devuelve el código que se le indique por encoder."""

    def __init__(self, codes=None, raises=None):
        self.codes, self.raises, self.calls = codes or {}, raises or {}, []

    def __call__(self, cmd, **kwargs):
        encoder = cmd[cmd.index("-c:v") + 1]
        self.calls.append((encoder, kwargs))
        if encoder in self.raises:
            raise self.raises[encoder]
        return subprocess.CompletedProcess(cmd, self.codes.get(encoder, 0))


def test_detection_marks_each_encoder_by_whether_ffmpeg_accepted_it():
    run = FakeRun({"h264_nvenc": 0, "h264_amf": 1, "h264_qsv": 1})
    assert video_encoding.detect_available("ffmpeg", run) == {
        "cpu": True, "nvidia": True, "amd": False, "intel": False,
    }
    assert [encoder for encoder, _ in run.calls] == ["h264_nvenc", "h264_amf", "h264_qsv"]  # cpu no se prueba
    assert all(kwargs["timeout"] == 5 for _, kwargs in run.calls)


def test_detection_never_raises_whatever_goes_wrong():
    run = FakeRun(raises={
        "h264_nvenc": subprocess.TimeoutExpired("ffmpeg", 5),
        "h264_amf": FileNotFoundError("ffmpeg"),
        "h264_qsv": RuntimeError("boom"),
    })
    assert video_encoding.detect_available("ffmpeg", run) == {
        "cpu": True, "nvidia": False, "amd": False, "intel": False,
    }


def test_the_probe_detects_only_once_however_many_times_it_is_asked():
    run = FakeRun({"h264_nvenc": 0, "h264_amf": 1, "h264_qsv": 1})
    probe = video_encoding.EncoderProbe("ffmpeg", run)
    first, second = probe.available(), probe.available()
    assert first == second == {"cpu": True, "nvidia": True, "amd": False, "intel": False}
    assert len(run.calls) == 3  # un solo recorrido por los 3 encoders de hardware


def test_the_probe_hands_out_copies_so_the_cache_cannot_be_altered():
    probe = video_encoding.EncoderProbe("ffmpeg", FakeRun())
    probe.available()["cpu"] = False
    assert probe.available()["cpu"] is True


# ── AudioToVideoOptions ──────────────────────────────────────────────────


def test_minimal_options_get_the_documented_defaults(tmp_path):
    opts = options(tmp_path)
    assert (opts.encoder, opts.fps, opts.crf, opts.resolution, opts.copy_audio) == ("cpu", 1, 23, "1280x720", True)
    assert (opts.background_image, opts.durations, opts.job_id) == (None, None, None)


@pytest.mark.parametrize("encoder, preset", [("cpu", "medium"), ("nvidia", "p4"), ("amd", "medium"), ("intel", "medium")])
def test_a_missing_preset_is_the_default_of_that_encoder(tmp_path, encoder, preset):
    assert options(tmp_path, encoder=encoder).preset == preset
    assert options(tmp_path, encoder=encoder).to_config().preset == preset


def test_options_must_be_an_object():
    with pytest.raises(ValueError, match="objeto"):
        AudioToVideoOptions.from_dict(["a"])


def test_unknown_keys_are_rejected_including_the_old_positional_and_view_ones(tmp_path):
    with pytest.raises(ValueError, match="Opciones desconocidas: copyAudio, showAdvanced"):
        options(tmp_path, copyAudio=True, showAdvanced=False)


def test_missing_keys_are_listed(tmp_path):
    with pytest.raises(ValueError, match="Faltan opciones: file_paths, base_folder"):
        AudioToVideoOptions.from_dict({})


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"file_paths": []}, "al menos un audio"),
        ({"file_paths": "a.mp3"}, "file_paths"),
        ({"file_paths": [""]}, "file_paths"),
        ({"base_folder": ""}, "base_folder"),
        ({"background_image": ""}, "background_image"),
        ({"encoder": "amd2"}, "encoder"),
        ({"fps": 25}, "fps"),
        ({"fps": 1.5}, "fps"),
        ({"fps": True}, "fps"),
        ({"crf": -1}, "entre 0 y 51"),
        ({"crf": 52}, "entre 0 y 51"),
        ({"crf": "23"}, "crf"),
        ({"preset": "p4"}, "no existe para el encoder «cpu»"),
        ({"encoder": "nvidia", "preset": "medium"}, "no existe para el encoder «nvidia»"),
        ({"resolution": "800x600"}, "resolution"),
        ({"copy_audio": "yes"}, "copy_audio"),
        ({"durations": [1, 2]}, "durations"),
        ({"durations": ["a"]}, "durations"),
        ({"durations": [-1]}, "durations"),
        ({"job_id": ""}, "job_id"),
    ],
)
def test_invalid_values_are_rejected_with_a_readable_message(tmp_path, overrides, message):
    with pytest.raises(ValueError, match=message):
        options(tmp_path, **overrides)


def test_the_error_for_an_unknown_preset_lists_the_valid_ones(tmp_path):
    with pytest.raises(ValueError, match="p1, p2, p3, p4, p5, p6, p7"):
        options(tmp_path, encoder="nvidia", preset="fast")


def test_whole_numbers_sent_as_floats_are_accepted(tmp_path):
    opts = options(tmp_path, fps=24.0, crf=18.0)
    assert (opts.fps, opts.crf) == (24, 18) and isinstance(opts.fps, int) and isinstance(opts.crf, int)


def test_unknown_durations_may_be_null_or_zero(tmp_path):
    assert options(tmp_path, durations=[None]).durations == [None]
    assert options(tmp_path, durations=[0]).durations == [0]


def test_to_config_resolves_paths(tmp_path):
    img = tmp_path / "images" / "bg.jpg"
    cfg = options(tmp_path, background_image=str(img), encoder="nvidia", crf=20, copy_audio=False).to_config()
    assert cfg.input_files == [tmp_path / "audios" / "ep1.mp3"]
    assert (cfg.base_folder, cfg.background_image) == (tmp_path, img)
    assert (cfg.encoder, cfg.crf, cfg.preset, cfg.copy_audio) == ("nvidia", 20, "p4", False)


# ── resolve_audio_to_video ───────────────────────────────────────────────


class Probe:
    def __init__(self, values=None, error=None):
        self.values, self.error, self.calls = values or {}, error, []

    def __call__(self, path):
        self.calls.append(path.name)
        if self.error:
            raise self.error
        return self.values.get(path.name, 42.0)


def test_known_durations_are_used_without_probing(tmp_path):
    make_files(tmp_path, "ep1.mp3")
    probe = Probe()
    inputs = resolve_audio_to_video(options(tmp_path, durations=[10.5]), probe)
    assert inputs.durations == [10.5] and isinstance(inputs.durations[0], float)
    assert probe.calls == []


def test_only_missing_or_zero_durations_are_probed(tmp_path):
    names = ["a.mp3", "b.mp3", "c.mp3", "d.mp3"]
    make_files(tmp_path, *names)
    probe = Probe({"b.mp3": 7.0, "d.mp3": 3.0})
    opts = options(tmp_path, file_paths=[str(tmp_path / "audios" / n) for n in names], durations=[10, None, 5, 0])
    assert resolve_audio_to_video(opts, probe).durations == [10.0, 7.0, 5.0, 3.0]
    assert probe.calls == ["b.mp3", "d.mp3"]


def test_without_any_durations_all_are_probed(tmp_path):
    make_files(tmp_path, "ep1.mp3")
    probe = Probe()
    assert resolve_audio_to_video(options(tmp_path), probe).durations == [42.0]
    assert probe.calls == ["ep1.mp3"]


def test_an_unreadable_file_gives_a_readable_error_naming_it(tmp_path):
    make_files(tmp_path, "ep1.mp3")
    with pytest.raises(ValueError, match="No se pudo leer la duración de «ep1.mp3»"):
        resolve_audio_to_video(options(tmp_path), Probe(error=ValueError("x")))


def test_a_missing_base_folder_is_an_error_not_a_folder_created_out_of_nowhere(tmp_path):
    make_files(tmp_path, "ep1.mp3")
    ghost = tmp_path / "no_existe"
    with pytest.raises(ValueError, match="La carpeta base no existe"):
        resolve_audio_to_video(options(tmp_path, base_folder=str(ghost)), Probe())
    assert not ghost.exists()


def test_a_missing_audio_is_an_error_naming_it(tmp_path):
    with pytest.raises(ValueError, match="No se encontró el archivo «ep1.mp3»"):
        resolve_audio_to_video(options(tmp_path), Probe())


def test_a_missing_background_image_is_an_error(tmp_path):
    make_files(tmp_path, "ep1.mp3")
    with pytest.raises(ValueError, match="No se encontró la imagen de fondo"):
        resolve_audio_to_video(options(tmp_path, background_image=str(tmp_path / "x.jpg")), Probe())


# ── Plan ─────────────────────────────────────────────────────────────────


def plan_for(tmp_path, names, durations=None, **overrides):
    make_files(tmp_path, *names)
    opts = options(tmp_path, file_paths=[str(tmp_path / "audios" / n) for n in names],
                   durations=durations or [10.0] * len(names), **overrides)
    inputs = resolve_audio_to_video(opts, Probe())
    return AudioToVideoAction().plan(inputs.config, inputs.durations)


def test_each_audio_gets_a_video_in_base_videos(tmp_path):
    plan = plan_for(tmp_path, ["a.mp3", "b.wav"], durations=[10.0, 5.0])
    assert plan.output_dir == tmp_path / "videos"
    assert [(f.name, f.output) for f in plan.files] == [
        ("a.mp3", tmp_path / "videos" / "a.mp4"),
        ("b.wav", tmp_path / "videos" / "b.mp4"),
    ]
    assert [f.duration for f in plan.files] == [10.0, 5.0] and plan.total_duration == 15.0


def test_the_plan_marks_outputs_that_already_exist(tmp_path):
    (tmp_path / "videos").mkdir()
    (tmp_path / "videos" / "b.mp4").write_bytes(b"old")
    plan = plan_for(tmp_path, ["a.mp3", "b.mp3"])
    assert [f.exists for f in plan.files] == [False, True]


def test_two_audios_that_give_the_same_video_are_an_error_naming_both(tmp_path):
    with pytest.raises(ValueError, match="«a.mp3» y «a.wav» darían el mismo video"):
        plan_for(tmp_path, ["a.mp3", "a.wav"])


def test_the_collision_check_ignores_case_like_windows_does(tmp_path):
    with pytest.raises(ValueError, match="darían el mismo video"):
        plan_for(tmp_path, ["Ep.mp3", "ep.wav"])


def test_a_too_long_output_path_is_an_error(tmp_path):
    cfg = AudioToVideoConfig([tmp_path / ("x" * 250 + ".mp3")], tmp_path, None)  # el plan no mira el disco
    with pytest.raises(ValueError, match="demasiado larga para Windows"):
        AudioToVideoAction().plan(cfg, [1.0])


def test_planning_has_no_side_effects(tmp_path):
    plan_for(tmp_path, ["a.mp3"])
    assert not (tmp_path / "videos").exists()


def test_plan_to_dict_shape(tmp_path):
    (tmp_path / "videos").mkdir()
    (tmp_path / "videos" / "a.mp4").write_bytes(b"old")
    d = plan_for(tmp_path, ["a.mp3", "b.mp3"], durations=[10.0, 5.0]).to_dict()
    assert d["output_dir"] == str(tmp_path / "videos")
    assert d["total_duration"] == 15.0
    assert d["files"][0] == {
        "index": 0, "name": "a.mp3", "path": str(tmp_path / "audios" / "a.mp3"), "duration": 10.0,
        "output": str(tmp_path / "videos" / "a.mp4"), "output_name": "a.mp4", "exists": True,
    }
    assert d["files"][1]["exists"] is False


# ── Comandos ─────────────────────────────────────────────────────────────


def a2v_config(tmp_path, **overrides):
    values = dict(input_files=[tmp_path / "ep1.mp3"], base_folder=tmp_path, background_image=None)
    values.update(overrides)
    return AudioToVideoConfig(**values)


def commands(cfg, durations=None):
    action = AudioToVideoAction()
    plan = action.plan(cfg, durations or [10.0] * len(cfg.input_files))
    return action.build_commands(cfg, plan)


def test_default_cpu_black_background(tmp_path):
    args = commands(a2v_config(tmp_path))[0].args
    assert args == [
        "-y", "-f", "lavfi", "-i", "color=c=black:s=1280x720:r=1",
        "-i", str(tmp_path / "ep1.mp3"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "1", "-crf", "23", "-preset", "medium",
        "-c:a", "copy", "-shortest",
        str(tmp_path / "videos" / "ep1.mp4"),
    ]


def test_with_image_uses_loop_stillimage_tune_even_dimensions_and_420(tmp_path):
    img = tmp_path / "bg.jpg"
    args = commands(a2v_config(tmp_path, background_image=img))[0].args
    assert args[1:6] == ["-framerate", "1", "-loop", "1", "-i"] and args[6] == str(img)
    assert args[args.index("-tune") + 1] == "stillimage"
    assert args[args.index("-vf") + 1] == "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    assert args[args.index("-pix_fmt") + 1] == "yuv420p"


def test_the_black_background_needs_no_scaling_filter(tmp_path):
    assert "-vf" not in commands(a2v_config(tmp_path))[0].args


def test_the_chosen_resolution_only_matters_without_image(tmp_path):
    black = commands(a2v_config(tmp_path, resolution="1920x1080"))[0].args
    assert "color=c=black:s=1920x1080:r=1" in black
    with_image = commands(a2v_config(tmp_path, resolution="1920x1080", background_image=tmp_path / "bg.jpg"))[0].args
    assert not any("1920x1080" in a for a in with_image)


@pytest.mark.parametrize(
    "encoder, codec, quality",
    [
        ("nvidia", "h264_nvenc", ["-cq", "23", "-tune", "hq"]),
        ("amd", "h264_amf", ["-qp", "23"]),
        ("intel", "h264_qsv", ["-qp", "23"]),
    ],
)
def test_hardware_encoders(tmp_path, encoder, codec, quality):
    args = commands(a2v_config(tmp_path, encoder=encoder))[0].args
    assert args[args.index("-c:v") + 1] == codec
    i = args.index(quality[0])
    assert args[i:i + len(quality)] == quality


@pytest.mark.parametrize("encoder", ["nvidia", "amd", "intel"])
def test_hardware_encoders_keep_negotiating_their_own_pixel_format_but_still_get_even_dimensions(tmp_path, encoder):
    args = commands(a2v_config(tmp_path, encoder=encoder, background_image=tmp_path / "bg.jpg"))[0].args
    assert "-pix_fmt" not in args
    assert "-vf" in args


def test_reencode_audio_and_empty_preset(tmp_path):
    args = commands(a2v_config(tmp_path, copy_audio=False, preset=""))[0].args
    assert "-preset" not in args
    assert args[args.index("-c:a"):args.index("-c:a") + 4] == ["-c:a", "aac", "-b:a", "192k"]


def test_one_command_per_audio_with_its_duration_output_and_label(tmp_path):
    cfg = a2v_config(tmp_path, input_files=[tmp_path / "a.mp3", tmp_path / "b.wav"])
    cmds = commands(cfg, durations=[10.0, 5.0])
    assert [(c.duration, c.output, c.label) for c in cmds] == [
        (10.0, tmp_path / "videos" / "a.mp4", "a.mp3"),
        (5.0, tmp_path / "videos" / "b.mp4", "b.wav"),
    ]
    assert cmds[0].args[-1] == str(tmp_path / "videos" / "a.mp4")


def test_building_the_commands_creates_nothing_on_disk(tmp_path):
    commands(a2v_config(tmp_path))
    assert not (tmp_path / "videos").exists()
