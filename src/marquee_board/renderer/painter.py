"""Frame painter — renders a FrameLayout to a PIL Image.

Takes the positioned elements from the layout engine and draws them
onto an RGB PIL Image at the exact pixel dimensions of the LED matrix.
Text elements support optional max_width constraints with truncation
("..") or time-based horizontal scrolling for long content.
"""

import logging
import time as _time
from typing import Tuple

from PIL import Image, ImageDraw

from .engine import FrameLayout, TextElement, IconElement, RectElement
from .fonts import FontManager
from .icons import get_icon
from . import colors

logger = logging.getLogger(__name__)

# Scroll tuning
_SCROLL_PAUSE = 2.0    # seconds to pause at each end
_SCROLL_SPEED = 20.0   # pixels per second


class FramePainter:
    """Renders a FrameLayout to a PIL Image."""

    def __init__(self, width: int = 64, height: int = 64):
        self.width = width
        self.height = height
        self._fonts = FontManager()

    def paint(self, layout: FrameLayout) -> Image.Image:
        """Render all elements in the layout to an RGB PIL Image."""
        img = Image.new("RGB", (self.width, self.height), colors.BG_COLOR)
        draw = ImageDraw.Draw(img)

        for element in layout.elements:
            if isinstance(element, RectElement):
                self._draw_rect(draw, element)
            elif isinstance(element, TextElement):
                self._draw_text(draw, img, element)
            elif isinstance(element, IconElement):
                self._draw_icon(img, element)

        return img

    def _draw_rect(self, draw: ImageDraw.ImageDraw, el: RectElement):
        draw.rectangle(
            [el.x, el.y, el.x + el.w - 1, el.y + el.h - 1],
            fill=el.color,
        )

    def _draw_text(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        el: TextElement,
    ):
        font = self._fonts.get(el.font_name)

        # No width constraint → draw as-is (PIL clips at image edge)
        if el.max_width is None or el.max_width <= 0:
            draw.text((el.x, el.y), el.text, fill=el.color, font=font)
            return

        text_w = self._fonts.text_width(el.text, el.font_name)

        # Fits within constraint → draw normally
        if text_w <= el.max_width:
            draw.text((el.x, el.y), el.text, fill=el.color, font=font)
            return

        if el.scroll:
            self._draw_scrolling_text(draw, img, el, font, text_w)
        else:
            self._draw_truncated_text(draw, img, el, font)

    def _draw_truncated_text(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        el: TextElement,
        font,
    ):
        """Truncate text with '..' to fit within max_width."""
        ellipsis = ".."
        ew = self._fonts.text_width(ellipsis, el.font_name)
        truncated = el.text
        while (
            len(truncated) > 1
            and self._fonts.text_width(truncated, el.font_name) + ew > el.max_width
        ):
            truncated = truncated[:-1]
        draw.text(
            (el.x, el.y),
            truncated.rstrip() + ellipsis,
            fill=el.color,
            font=font,
        )

    def _draw_scrolling_text(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        el: TextElement,
        font,
        text_w: int,
    ):
        """Render text with time-based horizontal scrolling.

        Cycle: pause at start → scroll left → pause at end → scroll right.
        Uses wall-clock time so each frame request gets the right offset
        without any stored state.
        """
        overflow = text_w - el.max_width
        scroll_dur = overflow / _SCROLL_SPEED
        cycle = _SCROLL_PAUSE + scroll_dur + _SCROLL_PAUSE + scroll_dur
        t = _time.time() % cycle

        if t < _SCROLL_PAUSE:
            offset = 0
        elif t < _SCROLL_PAUSE + scroll_dur:
            frac = (t - _SCROLL_PAUSE) / scroll_dur
            offset = int(frac * overflow)
        elif t < _SCROLL_PAUSE + scroll_dur + _SCROLL_PAUSE:
            offset = overflow
        else:
            frac = (t - 2 * _SCROLL_PAUSE - scroll_dur) / scroll_dur
            offset = int(overflow * (1 - frac))

        offset = max(0, min(offset, overflow))

        # Render full text onto a transparent temp image, then crop and
        # paste using the alpha channel as mask so only text pixels transfer
        # (no opaque black rectangle that overwrites content below).
        _, text_h = self._fonts.measure(el.text, el.font_name)
        pad = 4
        color_rgba = el.color + (255,) if len(el.color) == 3 else el.color
        tmp = Image.new("RGBA", (text_w + pad, text_h + pad), (0, 0, 0, 0))
        tmp_draw = ImageDraw.Draw(tmp)
        tmp_draw.text((0, 0), el.text, fill=color_rgba, font=font)

        crop_right = min(offset + el.max_width, text_w + pad)
        crop = tmp.crop((offset, 0, crop_right, text_h + pad))
        rgb = crop.convert("RGB")
        alpha = crop.split()[3]
        img.paste(rgb, (el.x, el.y), alpha)

    def _draw_icon(self, img: Image.Image, el: IconElement):
        icon_data = get_icon(el.icon_name, el.size)
        if not icon_data:
            return

        for row_idx, row in enumerate(icon_data):
            for col_idx, pixel in enumerate(row):
                if pixel != (0, 0, 0):
                    px = el.x + col_idx
                    py = el.y + row_idx
                    if 0 <= px < self.width and 0 <= py < self.height:
                        img.putpixel((px, py), pixel)
