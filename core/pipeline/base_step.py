from abc import ABC, abstractmethod
from typing import Callable

import customtkinter as ctk

from core.ffmpeg_runner import FFmpegRunner
from core.pipeline.context import PipelineContext


class BaseStep(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def open_config_modal(self, parent: ctk.CTk) -> None:
        pass

    @abstractmethod
    def execute(
        self,
        context: PipelineContext,
        runner: FFmpegRunner,
        on_log: Callable[[str], None],
        on_done: Callable[[bool, PipelineContext], None],
    ) -> None:
        pass