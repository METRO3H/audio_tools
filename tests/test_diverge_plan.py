"""
Plan de diverge (nombres, rutas, duraciones) y resolución de entradas.
El plan es la fuente única: el preview del frontend y la ejecución lo comparten.
"""
from pathlib import Path

import pytest

from core.actions.diverge_audio import DivergeAudioAction, resolve_diverge
from core.filenames import SAFE_PATH_LIMIT, utf16_len
from core.models import DivergeOptions


def options(tmp_path, **overrides):
    raw = {
        "file_path": str(tmp_path / "show.mp3"),
        "base_folder": str(tmp_path / "Proj"),
        "interval_seconds": 30,
    }
    raw.update(overrides)
    return DivergeOptions.from_dict({k: v for k, v in raw.items() if v is not ...})


class Probes:
    """Sondas falsas que registran cuántas veces se las consulta."""

    def __init__(self, duration=100.0, chapters=None, duration_error=None):
        self._duration, self._chapters, self._error = duration, chapters, duration_error
        self.duration_calls, self.chapter_calls = [], []

    def get_duration(self, path):
        self.duration_calls.append(path)
        if self._error:
            raise self._error
        return self._duration

    def get_chapters(self, path):
        self.chapter_calls.append(path)
        return self._chapters or []


# ── resolve_diverge ──────────────────────────────────────────────────────


def test_interval_mode_with_known_duration_does_not_probe(tmp_path):
    probes = Probes()
    inputs = resolve_diverge(options(tmp_path, duration_seconds=95.5), probes.get_duration, probes.get_chapters)
    assert inputs.duration == 95.5 and inputs.chapters is None
    assert probes.duration_calls == [] and probes.chapter_calls == []


def test_interval_mode_without_duration_reads_it_from_the_file(tmp_path):
    probes = Probes(duration=123.0)
    inputs = resolve_diverge(options(tmp_path), probes.get_duration, probes.get_chapters)
    assert inputs.duration == 123.0
    assert probes.duration_calls == [tmp_path / "show.mp3"]
    assert probes.chapter_calls == []


def test_unreadable_duration_gives_a_readable_error(tmp_path):
    probes = Probes(duration_error=ValueError("could not convert string to float: ''"))
    with pytest.raises(ValueError, match="No se pudo leer la duración de «show.mp3»"):
        resolve_diverge(options(tmp_path), probes.get_duration, probes.get_chapters)


def test_chapters_mode_reads_chapters_from_the_file_and_normalizes_them(tmp_path):
    found = [
        {"index": 1, "title": "Intro", "start": 0.0, "end": 12.5},
        {"index": 2, "title": None, "start": 12.5, "end": 40.0},
    ]
    probes = Probes(chapters=found)
    inputs = resolve_diverge(
        options(tmp_path, segment_mode="chapters", interval_seconds=None),
        probes.get_duration, probes.get_chapters,
    )
    assert inputs.chapters == [
        {"start": 0.0, "end": 12.5, "title": "Intro"},
        {"start": 12.5, "end": 40.0, "title": ""},
    ]
    assert probes.chapter_calls == [tmp_path / "show.mp3"]
    assert probes.duration_calls == []  # en modo chapters la duración no hace falta


def test_chapters_mode_on_a_file_without_chapters_is_an_error(tmp_path):
    probes = Probes(chapters=[])
    with pytest.raises(ValueError, match="no tiene capítulos"):
        resolve_diverge(
            options(tmp_path, segment_mode="chapters", interval_seconds=None),
            probes.get_duration, probes.get_chapters,
        )


def test_resolved_config_has_the_effective_output_folder(tmp_path):
    probes = Probes()
    inputs = resolve_diverge(options(tmp_path), probes.get_duration, probes.get_chapters)
    assert inputs.config.output_folder == tmp_path / "Proj"


# ── plan ─────────────────────────────────────────────────────────────────


def plan_for(tmp_path, **overrides):
    probes = Probes()
    inputs = resolve_diverge(options(tmp_path, **overrides), probes.get_duration, probes.get_chapters)
    return DivergeAudioAction().plan(inputs.config, inputs.duration, inputs.chapters), inputs


def test_plan_to_dict_shape_for_interval_mode(tmp_path):
    plan, _ = plan_for(tmp_path, duration_seconds=100)
    out = tmp_path / "Proj" / "audios" / "parts"
    assert plan.to_dict() == {
        "output_dir": str(out),
        "segments": [
            {"index": 1, "name": "[1] Proj.mp3", "start": 0, "end": 30, "duration": 30, "output": str(out / "[1] Proj.mp3")},
            {"index": 2, "name": "[2] Proj.mp3", "start": 30, "end": 60, "duration": 30, "output": str(out / "[2] Proj.mp3")},
            {"index": 3, "name": "[3] Proj.mp3", "start": 60, "end": 80.0, "duration": 20.0, "output": str(out / "[3] Proj.mp3")},
            {"index": 4, "name": "[4] Proj.mp3", "start": 80.0, "end": 100, "duration": 20.0, "output": str(out / "[4] Proj.mp3")},
        ],
    }


def test_plan_segment_count_equals_ceil_of_duration_over_interval(tmp_path):
    # el "N segmentos" que muestra el frontend sale de aquí
    import math
    for duration in (20, 90, 95, 100, 102, 105, 110):
        plan, _ = plan_for(tmp_path, duration_seconds=duration)
        assert len(plan.segments) == math.ceil(duration / 30)


def test_plan_with_chapters_uses_titles_and_real_durations(tmp_path):
    probes = Probes(chapters=[
        {"title": "Intro", "start": 0.0, "end": 12.5},
        {"title": "Main", "start": 12.5, "end": 99.0},
    ])
    inputs = resolve_diverge(
        options(tmp_path, segment_mode="chapters", interval_seconds=None),
        probes.get_duration, probes.get_chapters,
    )
    plan = DivergeAudioAction().plan(inputs.config, inputs.duration, inputs.chapters)
    assert [s.filename for s in plan.segments] == ["[1] Proj - Intro.mp3", "[2] Proj - Main.mp3"]
    assert [s.duration for s in plan.segments] == [12.5, 86.5]


def test_video_plan_names_after_the_file_and_writes_next_to_it(tmp_path):
    plan, _ = plan_for(tmp_path, file_path=str(tmp_path / "clip.mp4"), media_type="video", duration_seconds=40)
    assert plan.output_dir == tmp_path / "videos" / "parts"
    assert [s.filename for s in plan.segments] == ["[1] clip.mp4", "[2] clip.mp4"]


def test_plan_without_subfolder_writes_to_the_chosen_folder(tmp_path):
    plan, _ = plan_for(tmp_path, use_subfolder=False, output_folder=str(tmp_path / "salida"), duration_seconds=30)
    assert plan.output_dir == tmp_path / "salida"


def test_plan_has_no_side_effects(tmp_path):
    plan_for(tmp_path, duration_seconds=100)
    assert not (tmp_path / "Proj").exists()


# ── La propiedad central: lo que se previsualiza es lo que se ejecuta ─────


@pytest.mark.parametrize(
    "overrides",
    [
        {"duration_seconds": 100},                                        # intervalo, resto repartido
        {"duration_seconds": 110},                                        # intervalo, resto propio
        {"duration_seconds": 100, "output_format": "wav"},                # conversión de formato
        {"duration_seconds": 40, "media_type": "video", "file_path": "clip.mp4"},
        {"duration_seconds": 30, "use_subfolder": False, "output_folder": "salida"},
    ],
)
def test_plan_and_commands_agree(tmp_path, overrides):
    overrides = dict(overrides)
    for key in ("file_path", "output_folder"):
        if key in overrides:
            overrides[key] = str(tmp_path / overrides[key])
    plan, inputs = plan_for(tmp_path, **overrides)

    commands = DivergeAudioAction().build_commands(inputs.config, inputs.duration, inputs.chapters)

    assert [c.output for c in commands] == [s.output for s in plan.segments]
    assert [c.label for c in commands] == [s.filename for s in plan.segments]
    assert [c.duration for c in commands] == [s.duration for s in plan.segments]
    assert all(c.args[-1] == str(s.output) for c, s in zip(commands, plan.segments))
    assert plan.output_dir.is_dir()  # solo build_commands crea la carpeta


# ── Nombres: los títulos de capítulo se limpian y se ajustan a la ruta ───


def chapter_plan(tmp_path, titles, **overrides):
    probes = Probes(chapters=[
        {"title": title, "start": i * 10.0, "end": (i + 1) * 10.0} for i, title in enumerate(titles)
    ])
    inputs = resolve_diverge(
        options(tmp_path, segment_mode="chapters", interval_seconds=None, **overrides),
        probes.get_duration, probes.get_chapters,
    )
    return DivergeAudioAction().plan(inputs.config, inputs.duration, inputs.chapters), inputs


def test_chapter_titles_with_invalid_characters_are_cleaned(tmp_path):
    plan, _ = chapter_plan(tmp_path, ["Parte 1: Intro", "Q/A *final*?", "<Extra> | bonus"])
    assert [s.filename for s in plan.segments] == [
        "[1] Proj - Parte 1 - Intro.mp3",
        "[2] Proj - Q-A final.mp3",
        "[3] Proj - (Extra) - bonus.mp3",
    ]
    # ":" en el nombre crearía un stream alterno NTFS en vez de fallar
    assert not any(set('<>:"/\\|?*') & set(s.filename) for s in plan.segments)


def test_a_title_that_cleans_to_nothing_leaves_the_file_without_title(tmp_path):
    plan, _ = chapter_plan(tmp_path, ["???", "Real", ":"])
    assert [s.filename for s in plan.segments] == ["[1] Proj.mp3", "[2] Proj - Real.mp3", "[3] Proj.mp3"]


def test_fullwidth_punctuation_in_titles_is_preserved(tmp_path):
    plan, _ = chapter_plan(tmp_path, ["第１章：はじめに"])
    assert plan.segments[0].filename == "[1] Proj - 第１章：はじめに.mp3"


def test_long_title_is_cut_so_the_whole_path_stays_under_the_limit(tmp_path):
    plan, _ = chapter_plan(tmp_path, ["x" * 500, "Corto"])
    long, short = plan.segments
    assert utf16_len(str(long.output)) <= SAFE_PATH_LIMIT
    assert long.filename.startswith("[1] Proj - xxxxxxxxxx") and long.filename.endswith("x.mp3")
    assert len(long.filename) > len("[1] Proj - .mp3") + 10
    assert short.filename == "[2] Proj - Corto.mp3"  # lo que cabe no se toca


def test_when_the_directory_leaves_no_room_the_title_is_dropped(tmp_path):
    deep = tmp_path / ("d" * 215)  # la carpeta de salida por sí sola casi agota el límite
    plan, _ = chapter_plan(tmp_path, ["Un título largo y descriptivo"], use_subfolder=False, output_folder=str(deep))
    assert plan.segments[0].filename == "[1] Proj.mp3"


def test_commands_write_exactly_the_cleaned_paths_of_the_plan(tmp_path):
    plan, inputs = chapter_plan(tmp_path, ["Parte 1: Intro", "x" * 500, "???"])
    commands = DivergeAudioAction().build_commands(inputs.config, inputs.duration, inputs.chapters)
    assert [c.output for c in commands] == [s.output for s in plan.segments]
    assert [c.args[-1] for c in commands] == [str(s.output) for s in plan.segments]
    assert all(c.output.parent.is_dir() for c in commands)


def _valid_on_windows(filename: str) -> bool:
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    return (
        0 < len(filename) <= 255
        and not (set('<>:"/\\|?*') & set(filename))
        and not any(ord(c) < 32 for c in filename)
        and not filename.endswith((" ", "."))
        and filename.rsplit(".", 1)[0].upper() not in reserved
    )


def test_every_generated_name_is_valid_on_windows_and_fits_the_path_limit(tmp_path):
    import random

    rng = random.Random(7)
    alphabet = list('abc XYZ019:|/\\"<>?*-.\t\n\x00ñé日本語') + ["😀", "　", "：", "／"]
    for _ in range(300):
        titles = [
            "".join(rng.choice(alphabet) for _ in range(rng.choice([0, 3, 15, 80, 400])))
            for _ in range(rng.randint(1, 6))
        ]
        plan, _ = chapter_plan(tmp_path, titles)
        names = [s.filename for s in plan.segments]
        assert all(_valid_on_windows(n) for n in names), (titles, names)
        assert len(set(names)) == len(names), (titles, names)          # el índice [i] los mantiene únicos
        assert all(utf16_len(str(s.output)) <= SAFE_PATH_LIMIT for s in plan.segments), titles
