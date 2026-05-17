from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from core.ffmpeg_runner import FFmpegRunner
from core.pipeline.base_step import BaseStep
from core.pipeline.context import PipelineContext

if TYPE_CHECKING:
    from core.pipeline.step_hooks import StepProgressHooks


class PipelineExecutor:

    def execute(
        self,
        steps: list[BaseStep],
        context: PipelineContext,
        runner: FFmpegRunner,
        on_log: Callable[[str], None],
        on_done: Callable[[bool], None],
        get_hooks: Callable[[int], "StepProgressHooks | None"] | None = None,
        on_step_done: Callable[[int, bool], None] | None = None,
    ) -> None:
        self._run_step(
            steps, index=0, context=context, runner=runner,
            on_log=on_log, on_done=on_done,
            get_hooks=get_hooks, on_step_done=on_step_done,
        )

    def _run_step(
        self,
        steps: list[BaseStep],
        index: int,
        context: PipelineContext,
        runner: FFmpegRunner,
        on_log: Callable[[str], None],
        on_done: Callable[[bool], None],
        get_hooks: Callable[[int], "StepProgressHooks | None"] | None,
        on_step_done: Callable[[int, bool], None] | None,
    ) -> None:
        if index >= len(steps):
            on_done(True)
            return

        step = steps[index]
        on_log(f"[ {index + 1}/{len(steps)} ] {step.name}...")

        hooks = get_hooks(index) if get_hooks else None

        def done(success: bool, updated_context: PipelineContext):
            if on_step_done:
                on_step_done(index, success)
            if not success:
                on_done(False)
                return
            self._run_step(
                steps, index + 1, updated_context, runner,
                on_log, on_done, get_hooks, on_step_done,
            )

        try:
            step.execute(
                context=context,
                runner=runner,
                on_log=on_log,
                on_done=done,
                hooks=hooks,
            )
        except Exception as e:
            on_log(f"[error] {step.name}: {e}")
            if on_step_done:
                on_step_done(index, False)
            on_done(False)