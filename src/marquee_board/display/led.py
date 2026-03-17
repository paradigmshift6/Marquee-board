"""LED matrix display backend using rpi-rgb-led-matrix (hzeller).

Only works on Raspberry Pi with a HUB75 LED panel connected.
The rgbmatrix library is imported lazily so the rest of the app
can run on any platform (web simulator, terminal, etc.).

Rendering is done on a dedicated thread at _TARGET_FPS so scrolling
and animations are smooth regardless of how often the main app loop
calls update() to push new provider data (typically every 2 s).
"""

import logging
import threading
import time
from typing import Dict, List, Optional

from .base import DisplayBackend

logger = logging.getLogger(__name__)

_TARGET_FPS = 25   # render thread target frame rate


class LEDDisplay(DisplayBackend):
    def __init__(
        self,
        width: int = 64,
        height: int = 64,
        brightness: int = 80,
        gpio_slowdown: int = 4,
        hardware_mapping: str = "adafruit-hat",
    ):
        self._width = width
        self._height = height
        self._brightness = brightness
        self._gpio_slowdown = gpio_slowdown
        self._hardware_mapping = hardware_mapping
        self._matrix = None
        self._engine = None
        self._painter = None

        # Shared state between main loop and render thread
        self._messages: List = []
        self._lock = threading.Lock()
        self._render_thread: Optional[threading.Thread] = None
        self._render_running = False

    def start(self) -> None:
        # Initialize renderer
        from ..renderer.engine import LayoutEngine
        from ..renderer.painter import FramePainter

        self._engine = LayoutEngine(self._width, self._height)
        self._painter = FramePainter(self._width, self._height)

        # Initialize LED matrix hardware
        try:
            from rgbmatrix import RGBMatrix, RGBMatrixOptions

            options = RGBMatrixOptions()
            options.rows = self._height
            options.cols = self._width
            options.brightness = self._brightness
            options.gpio_slowdown = self._gpio_slowdown
            options.hardware_mapping = self._hardware_mapping

            self._matrix = RGBMatrix(options=options)
            logger.info(
                "LED matrix initialized (%dx%d, brightness=%d)",
                self._width, self._height, self._brightness,
            )
        except ImportError:
            logger.error(
                "rpi-rgb-led-matrix not installed. "
                "Install with: pip install marquee-board[led]"
            )
            raise
        except Exception as e:
            logger.error("Failed to initialize LED matrix: %s", e)
            raise

        # Start the dedicated render thread
        self._render_running = True
        self._render_thread = threading.Thread(
            target=self._render_loop, name="led-render", daemon=True
        )
        self._render_thread.start()
        logger.info("LED render thread started at %d FPS", _TARGET_FPS)

    def update(
        self,
        grouped: Dict[str, List[str]],
        display_names: Dict[str, str],
        **kwargs,
    ) -> None:
        """Store the latest messages so the render thread can pick them up."""
        messages = kwargs.get("structured", [])
        with self._lock:
            self._messages = messages

    def stop(self) -> None:
        self._render_running = False
        if self._render_thread:
            self._render_thread.join(timeout=2)
        if self._matrix:
            self._matrix.Clear()
            logger.info("LED matrix cleared")

    # ------------------------------------------------------------------
    # Render thread
    # ------------------------------------------------------------------

    def _render_loop(self) -> None:
        """Render frames continuously at _TARGET_FPS.

        Reads the latest messages under a lock, lays them out, paints the
        frame, and pushes it to the matrix.  Because layout/paint use
        wall-clock time for scroll offsets, each frame naturally advances
        the animation without any extra state.
        """
        frame_budget = 1.0 / _TARGET_FPS
        while self._render_running:
            t0 = time.monotonic()
            try:
                with self._lock:
                    messages = list(self._messages)
                layout = self._engine.layout(messages)
                img = self._painter.paint(layout)
                self._matrix.SetImage(img)
            except Exception:
                logger.exception("Error in LED render loop")

            elapsed = time.monotonic() - t0
            remaining = frame_budget - elapsed
            if remaining > 0:
                time.sleep(remaining)
