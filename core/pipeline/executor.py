from typing import Callable

from core.ffmpeg_runner import FFmpegRunner
from core.pipeline.base_step import BaseStep
from core.pipeline.context import PipelineContext


class PipelineExecutor:

    def execute(
        self,
        steps: list[BaseStep],
        context: PipelineContext,
        runner: FFmpegRunner,
        on_log: Callable[[str], None],
        on_done: Callable[[bool], None],
    ) -> None:
        self._run_step(steps, index=0, context=context, runner=runner, on_log=on_log, on_done=on_done)

    def _run_step(
        self,
        steps: list[BaseStep],
        index: int,
        context: PipelineContext,
        runner: FFmpegRunner,
        on_log: Callable[[str], None],
        on_done: Callable[[bool], None],
    ) -> None:
        if index >= len(steps):
            on_done(True)
            return

        step = steps[index]
        on_log(f"[ {index + 1}/{len(steps)} ] {step.name}...")

        def done(success: bool, updated_context: PipelineContext):
            if not success:
                on_done(False)
                return
            self._run_step(steps, index + 1, updated_context, runner, on_log, on_done)

        try:
            step.execute(context=context, runner=runner, on_log=on_log, on_done=done)
        except Exception as e:
            on_log(f"[error] {step.name}: {e}")
            on_done(False)