__all__ = ["BaseSlide"]

import platform
from abc import abstractmethod
from pathlib import Path
from typing import Any, List, MutableMapping, Optional, Sequence, Tuple, ValuesView

import numpy as np
from tqdm import tqdm

from ..config import PresentationConfig, PreSlideConfig, SlideConfig
from ..defaults import FFMPEG_BIN, FOLDER_PATH
from ..logger import logger
from ..utils import concatenate_video_files, merge_basenames, reverse_video_file
from . import MANIM

if MANIM:
    from manim.mobject.mobject import Mobject
else:
    Mobject = Any


class BaseSlide:
    def __init__(
        self, *args: Any, output_folder: Path = FOLDER_PATH, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self._output_folder: Path = output_folder
        self._slides: List[PreSlideConfig] = []
        self._current_slide = 1
        self._current_animation = 0
        self._loop_start_animation: Optional[int] = None
        self._pause_start_animation = 0
        self._canvas: MutableMapping[str, Mobject] = {}
        self._wait_time_between_slides = 0.0

    @property
    def _ffmpeg_bin(self) -> Path:
        """Returns the path to the ffmpeg binaries."""
        return FFMPEG_BIN

    @property
    @abstractmethod
    def _frame_height(self) -> float:
        """Returns the scene's frame height."""
        ...

    @property
    @abstractmethod
    def _frame_width(self) -> float:
        """Returns the scene's frame width."""
        ...

    @property
    @abstractmethod
    def _background_color(self) -> str:
        """Returns the scene's background color."""
        ...

    @property
    @abstractmethod
    def _resolution(self) -> Tuple[int, int]:
        """Returns the scene's resolution used during rendering."""
        ...

    @property
    @abstractmethod
    def _partial_movie_files(self) -> List[Path]:
        """Returns a list of partial movie files, a.k.a animations."""
        ...

    @property
    @abstractmethod
    def _show_progress_bar(self) -> bool:
        """Returns True if progress bar should be displayed."""
        ...

    @property
    @abstractmethod
    def _leave_progress_bar(self) -> bool:
        """Returns True if progress bar should be left after completed."""
        ...

    @property
    @abstractmethod
    def _start_at_animation_number(self) -> Optional[int]:
        """If set, returns the animation number at which rendering start."""
        ...

    @property
    def canvas(self) -> MutableMapping[str, Mobject]:
        """
        Returns the canvas associated to the current slide.

        The canvas is a mapping between names and Mobjects,
        for objects that are assumed to stay in multiple slides.

        For example, a section title or a slide number.

        Examples
        --------

        .. manim-slides:: CanvasExample

            from manim import *
            from manim_slides import Slide

            class CanvasExample(Slide):
                def update_canvas(self):
                    self.counter += 1
                    old_slide_number = self.canvas["slide_number"]
                    new_slide_number = Text(f"{self.counter}").move_to(old_slide_number)
                    self.play(Transform(old_slide_number, new_slide_number))

                def construct(self):
                    title = Text("My Title").to_corner(UL)

                    self.counter = 1
                    slide_number = Text("1").to_corner(DL)

                    self.add_to_canvas(title=title, slide_number=slide_number)

                    self.play(FadeIn(title), FadeIn(slide_number))
                    self.next_slide()

                    circle = Circle(radius=2)
                    dot = Dot()

                    self.update_canvas()
                    self.play(Create(circle))
                    self.play(MoveAlongPath(dot, circle))

                    self.next_slide()
                    self.update_canvas()

                    square = Square()

                    self.wipe(self.mobjects_without_canvas, square)
                    self.next_slide()

                    self.update_canvas()
                    self.play(
                        Transform(
                            self.canvas["title"],
                            Text("New Title").to_corner(UL)
                        )
                    )
                    self.next_slide()

                    self.remove_from_canvas("title", "slide_number")
                    self.wipe(self.mobjects_without_canvas, [])
        """
        return self._canvas

    def add_to_canvas(self, **objects: Mobject) -> None:
        """
        Adds objects to the canvas, using key values as names.

        :param objects: A mapping between names and Mobjects.

        .. note::

            This method does not actually do anything in terms of
            animations. You must still call :code:`self.add` or
            play some animation that introduces each Mobject for
            it to appear. The same applies when removing objects.
        """
        self._canvas.update(objects)

    def remove_from_canvas(self, *names: str) -> None:
        """Removes objects from the canvas."""
        for name in names:
            self._canvas.pop(name)

    @property
    def canvas_mobjects(self) -> ValuesView[Mobject]:
        """Returns Mobjects contained in the canvas."""
        return self.canvas.values()

    @property
    def mobjects_without_canvas(self) -> Sequence[Mobject]:
        """Returns the list of objects contained in the scene, minus those present in
        the canvas."""
        return [
            mobject for mobject in self.mobjects if mobject not in self.canvas_mobjects  # type: ignore[attr-defined]
        ]

    @property
    def wait_time_between_slides(self) -> float:
        r"""
        Returns the wait duration (in seconds) added between two slides.

        By default, this value is set to 0.

        Setting this value to something bigger than 0 will result in a
        :code:`self.wait` animation called at the end of every slide.

        .. note::
            This is useful because animations are usually only terminated
            when a new animation is played. You can observe the small difference
            in the examples below: the circle is not fully complete in the first
            slide of the first example, but well in the second example.

        Examples
        --------

        .. manim-slides:: WithoutWaitExample

            from manim import *
            from manim_slides import Slide

            class WithoutWaitExample(Slide):
                def construct(self):
                    circle = Circle(radius=2)
                    arrow = Arrow().next_to(circle, RIGHT).scale(-1)
                    text = Text("Small\ngap").next_to(arrow, RIGHT)

                    self.play(Create(arrow), FadeIn(text))
                    self.play(Create(circle))
                    self.next_slide()

                    self.play(FadeOut(circle))

        .. manim-slides:: WithWaitExample

            from manim import *
            from manim_slides import Slide

            class WithWaitExample(Slide):
                def construct(self):
                    self.wait_time_between_slides = 0.1  # A small value > 1 / FPS
                    circle = Circle(radius=2)
                    arrow = Arrow().next_to(circle, RIGHT).scale(-1)
                    text = Text("No more\ngap").next_to(arrow, RIGHT)

                    self.play(Create(arrow), FadeIn(text))
                    self.play(Create(circle))
                    self.next_slide()

                    self.play(FadeOut(circle))
        """
        return self._wait_time_between_slides

    @wait_time_between_slides.setter
    def wait_time_between_slides(self, wait_time: float) -> None:
        self._wait_time_between_slides = max(wait_time, 0.0)

    def play(self, *args: Any, **kwargs: Any) -> None:
        """Overloads `self.play` and increment animation count."""
        super().play(*args, **kwargs)  # type: ignore[misc]
        self._current_animation += 1

    def next_slide(self) -> None:
        """
        Creates a new slide with previous animations.

        This usually means that the user will need to press some key before the
        next slide is played. By default, this is the right arrow key.


        .. note::

            Calls to :func:`next_slide` at the very beginning or at the end are
            not needed, since they are automatically added.

        .. warning::

            This is not allowed to call :func:`next_slide` inside a loop.

        Examples
        --------

        The following contains 3 slides:

        #. the first with nothing on it;
        #. the second with "Hello World!" fading in;
        #. and the last with the text fading out;

        .. manim-slides:: NextSlideExample

            from manim import *
            from manim_slides import Slide

            class NextSlideExample(Slide):
                def construct(self):
                    text = Text("Hello World!")

                    self.play(FadeIn(text))

                    self.next_slide()
                    self.play(FadeOut(text))
        """
        assert (
            self._loop_start_animation is None
        ), "You cannot call `self.next_slide()` inside a loop"

        if self.wait_time_between_slides > 0.0:
            self.wait(self.wait_time_between_slides)  # type: ignore[attr-defined]

        self._slides.append(
            PreSlideConfig(
                start_animation=self._pause_start_animation,
                end_animation=self._current_animation,
            )
        )
        self._current_slide += 1
        self._pause_start_animation = self._current_animation

    def _add_last_slide(self) -> None:
        """Adds a 'last' slide to the end of slides."""

        if (
            len(self._slides) > 0
            and self._current_animation == self._slides[-1].end_animation
        ):
            return

        self._slides.append(
            PreSlideConfig(
                start_animation=self._pause_start_animation,
                end_animation=self._current_animation,
                loop=self._loop_start_animation is not None,
            )
        )

    def start_loop(self) -> None:
        """
        Starts a loop. End it with :func:`end_loop`.

        A loop will automatically replay the slide, i.e., everything between
        :func:`start_loop` and :func:`end_loop`, upon reaching end.

        .. warning::

            You should always call :func:`next_slide` before calling this
            method. Otherwise, ...

        .. warning::

            When rendered with RevealJS, loops cannot be in the first nor
            the last slide.

        Examples
        --------

        The following contains one slide that will loop endlessly.

        .. manim-slides:: LoopExample

            from manim import *
            from manim_slides import Slide

            class LoopExample(Slide):
                def construct(self):
                    dot = Dot(color=BLUE, radius=1)

                    self.play(FadeIn(dot))
                    self.next_slide()

                    self.start_loop()

                    self.play(Indicate(dot, scale_factor=2))

                    self.end_loop()

                    self.play(FadeOut(dot))
        """
        assert self._loop_start_animation is None, "You cannot nest loops"
        self._loop_start_animation = self._current_animation

    def end_loop(self) -> None:
        """
        Ends an existing loop.

        See :func:`start_loop` for more details.
        """
        assert (
            self._loop_start_animation is not None
        ), "You have to start a loop before ending it"
        self._slides.append(
            PreSlideConfig(
                start_animation=self._loop_start_animation,
                end_animation=self._current_animation,
                loop=True,
            )
        )
        self._current_slide += 1
        self._loop_start_animation = None
        self._pause_start_animation = self._current_animation

    def _save_slides(self, use_cache: bool = True) -> None:
        """
        Saves slides, optionally using cached files.

        Note that cached files only work with Manim.
        """
        self._add_last_slide()

        files_folder = self._output_folder / "files"

        scene_name = str(self)
        scene_files_folder = files_folder / scene_name

        scene_files_folder.mkdir(parents=True, exist_ok=True)

        files: List[Path] = self._partial_movie_files

        # We must filter slides that end before the animation offset
        if offset := self._start_at_animation_number:
            self._slides = [
                slide for slide in self._slides if slide.end_animation > offset
            ]
            for slide in self._slides:
                slide.start_animation = max(0, slide.start_animation - offset)
                slide.end_animation -= offset

        slides: List[SlideConfig] = []

        for pre_slide_config in tqdm(
            self._slides,
            desc=f"Concatenating animation files to '{scene_files_folder}' and generating reversed animations",
            leave=self._leave_progress_bar,
            ascii=True if platform.system() == "Windows" else None,
            disable=not self._show_progress_bar,
        ):
            slide_files = files[pre_slide_config.slides_slice]

            file = merge_basenames(slide_files)
            dst_file = scene_files_folder / file.name
            rev_file = scene_files_folder / f"{file.stem}_reversed{file.suffix}"

            # We only concat animations if it was not present
            if not use_cache or not dst_file.exists():
                concatenate_video_files(self._ffmpeg_bin, slide_files, dst_file)

            # We only reverse video if it was not present
            if not use_cache or not rev_file.exists():
                reverse_video_file(self._ffmpeg_bin, dst_file, rev_file)

            slides.append(
                SlideConfig.from_pre_slide_config_and_files(
                    pre_slide_config, dst_file, rev_file
                )
            )

        logger.info(
            f"Generated {len(slides)} slides to '{scene_files_folder.absolute()}'"
        )

        slide_path = self._output_folder / f"{scene_name}.json"

        PresentationConfig(
            slides=slides,
            resolution=self._resolution,
            background_color=self._background_color,
        ).to_file(slide_path)

        logger.info(
            f"Slide '{scene_name}' configuration written in '{slide_path.absolute()}'"
        )

    def wipe(
        self,
        *args: Any,
        direction: np.ndarray = np.array([-1.0, 0.0, 0.0]),
        **kwargs: Any,
    ) -> None:
        """
        Plays a wipe animation that will shift all the current objects outside of the
        current scene's scope, and all the future objects inside.

        :param args: Positional arguments passed to
            :class:`Wipe<manim_slides.slide.animation.Wipe>`.
        :param direction: The wipe direction, that will be scaled by the scene size.
        :param kwargs: Keyword arguments passed to
            :class:`Wipe<manim_slides.slide.animation.Wipe>`.

        Examples
        --------

        .. manim-slides:: WipeExample

            from manim import *
            from manim_slides import Slide

            class WipeExample(Slide):
                def construct(self):
                    circle = Circle(radius=3, color=BLUE)
                    square = Square()
                    text = Text("This is a wipe example").next_to(square, DOWN)
                    beautiful = Text("Beautiful, no?")

                    self.play(FadeIn(circle))
                    self.next_slide()

                    self.wipe(circle, Group(square, text))
                    self.next_slide()

                    self.wipe(Group(square, text), beautiful, direction=UP)
                    self.next_slide()

                    self.wipe(beautiful, circle, direction=DOWN + RIGHT)
        """
        from .animation import Wipe

        shift_amount = np.asarray(direction) * np.array(
            [self._frame_width, self._frame_height, 0.0]
        )

        kwargs.setdefault("shift", shift_amount)

        animation = Wipe(
            *args,
            **kwargs,
        )

        self.play(animation)

    def zoom(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        Plays a zoom animation that will fade out all the current objects, and fade in
        all the future objects. Objects are faded in a direction that goes towards the
        camera.

        :param args: Positional arguments passed to
            :class:`Zoom<manim_slides.slide.animation.Zoom>`.
        :param kwargs: Keyword arguments passed to
            :class:`Zoom<manim_slides.slide.animation.Zoom>`.

        Examples
        --------

        .. manim-slides:: ZoomExample

            from manim import *
            from manim_slides import Slide

            class ZoomExample(Slide):
                def construct(self):
                    circle = Circle(radius=3, color=BLUE)
                    square = Square()

                    self.play(FadeIn(circle))
                    self.next_slide()

                    self.zoom(circle, square)
                    self.next_slide()

                    self.zoom(square, circle, out=True, scale=10.0)
        """
        from .animation import Zoom

        animation = Zoom(*args, **kwargs)

        self.play(animation)
