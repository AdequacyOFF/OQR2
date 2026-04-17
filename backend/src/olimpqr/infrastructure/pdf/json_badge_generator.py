"""Badge PDF generator driven by a JSON template config (ReportLab-based, no LibreOffice)."""

from __future__ import annotations

import io
import logging
import os
import re
from pathlib import Path
from typing import Any

from reportlab.lib import colors as rl_colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

logger = logging.getLogger(__name__)

# ── font registry ────────────────────────────────────────────────────────────

_REGISTERED_FONTS: set[str] = set()
_SCANNED_FONT_DIRS: set[str] = set()  # track dirs already globbed for custom fonts
_SYSTEM_FONTS_REGISTERED: bool = False  # track whether system fonts pass was done

_SYSTEM_FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu/",
    "/usr/share/fonts/truetype/liberation/",
    "/usr/share/fonts/truetype/freefont/",
]

_SYSTEM_FONT_CANDIDATES = [
    ("DejaVuSans", "DejaVuSans.ttf"),
    ("DejaVuSans-Bold", "DejaVuSans-Bold.ttf"),
    ("DejaVuSans-Oblique", "DejaVuSans-Oblique.ttf"),
    ("DejaVuSans-BoldOblique", "DejaVuSans-BoldOblique.ttf"),
    ("LiberationSans", "LiberationSans-Regular.ttf"),
    ("LiberationSans-Bold", "LiberationSans-Bold.ttf"),
    ("LiberationSans-Italic", "LiberationSans-Italic.ttf"),
    ("LiberationSans-BoldItalic", "LiberationSans-BoldItalic.ttf"),
]

_DEFAULT_FONT = "Helvetica"


def _try_register(name: str, path: str) -> bool:
    if name in _REGISTERED_FONTS:
        return True
    try:
        pdfmetrics.registerFont(TTFont(name, path))
        _REGISTERED_FONTS.add(name)
        return True
    except Exception as exc:
        logger.debug("Cannot register font %s from %s: %s", name, path, exc)
        return False


def _register_system_fonts() -> None:
    global _SYSTEM_FONTS_REGISTERED
    if _SYSTEM_FONTS_REGISTERED:
        return
    for name, filename in _SYSTEM_FONT_CANDIDATES:
        if name in _REGISTERED_FONTS:
            continue
        for font_dir in _SYSTEM_FONT_DIRS:
            full_path = os.path.join(font_dir, filename)
            if os.path.exists(full_path):
                _try_register(name, full_path)
                break
    _SYSTEM_FONTS_REGISTERED = True


def _register_custom_fonts(fonts_dir: Path) -> None:
    dir_key = str(fonts_dir)
    if dir_key in _SCANNED_FONT_DIRS:
        return
    if not fonts_dir.exists():
        _SCANNED_FONT_DIRS.add(dir_key)
        return
    for ttf_path in fonts_dir.glob("*.ttf"):
        name = ttf_path.stem
        _try_register(name, str(ttf_path))
    for otf_path in fonts_dir.glob("*.otf"):
        name = otf_path.stem
        _try_register(name, str(otf_path))
    _SCANNED_FONT_DIRS.add(dir_key)


def _resolve_font(
    family: str | None,
    bold: bool = False,
    italic: bool = False,
    fonts_dir: Path | None = None,
) -> str:
    """Return a registered ReportLab font name, with best-effort bold/italic variants."""
    _register_system_fonts()
    if fonts_dir:
        _register_custom_fonts(fonts_dir)

    if not family:
        family = "DejaVuSans"

    # Try exact name first (user may specify "Magistral-Bold" directly)
    if family in _REGISTERED_FONTS:
        return family

    # Try bold/italic variants
    candidates: list[str] = []
    if bold and italic:
        candidates += [f"{family}-BoldItalic", f"{family}-BoldOblique", f"{family}BoldItalic"]
    if bold:
        candidates += [f"{family}-Bold", f"{family}Bold"]
    if italic:
        candidates += [f"{family}-Italic", f"{family}-Oblique", f"{family}Italic"]
    candidates.append(family)

    for name in candidates:
        if name in _REGISTERED_FONTS:
            return name

    # Fallback chain: DejaVuSans variants → Helvetica
    fallback_map = {
        (True, True): ["DejaVuSans-BoldOblique", "Helvetica-BoldOblique"],
        (True, False): ["DejaVuSans-Bold", "Helvetica-Bold"],
        (False, True): ["DejaVuSans-Oblique", "Helvetica-Oblique"],
        (False, False): ["DejaVuSans", "Helvetica"],
    }
    for fb in fallback_map.get((bold, italic), []):
        if fb in _REGISTERED_FONTS or fb.startswith("Helvetica"):
            return fb

    return _DEFAULT_FONT


def _make_rounded_rect_path(c: rl_canvas.Canvas, x: float, y: float, w: float, h: float, r: float):
    """Return a closed path for a rounded rectangle using cubic Bézier approximation."""
    r = min(r, w / 2, h / 2)
    k = 0.5522847498  # = 4*(sqrt(2)-1)/3  — Bézier circle approximation constant
    p = c.beginPath()
    p.moveTo(x + r, y)
    p.lineTo(x + w - r, y)
    p.curveTo(x + w - r + k * r, y,          x + w,           y + r - k * r,  x + w,     y + r)
    p.lineTo(x + w, y + h - r)
    p.curveTo(x + w,           y + h - r + k * r, x + w - r + k * r, y + h,   x + w - r, y + h)
    p.lineTo(x + r, y + h)
    p.curveTo(x + r - k * r,   y + h,         x,               y + h - r + k * r, x,     y + h - r)
    p.lineTo(x, y + r)
    p.curveTo(x,               y + r - k * r, x + r - k * r,   y,               x + r,   y)
    p.close()
    return p


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    hex_color = (hex_color or "#000000").strip().lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    try:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return r / 255.0, g / 255.0, b / 255.0
    except Exception:
        return 0.0, 0.0, 0.0


# ── Main generator ────────────────────────────────────────────────────────────

class JsonBadgeGenerator:
    """Generate a single-page badge PDF from a JSON template config + participant data.

    Coordinate system in the JSON config uses (x_mm, y_mm) measured from the
    TOP-LEFT corner of the badge (more intuitive for a visual editor).
    ReportLab uses bottom-left origin, so we flip y inside this class.
    """

    FONTS_DIR = Path(__file__).resolve().parents[4] / "templates" / "word" / "fonts"

    def __init__(self, fonts_dir: Path | None = None):
        self.fonts_dir = fonts_dir or self.FONTS_DIR
        # Register fonts once per instance rather than on every generate_badge_pdf call.
        _register_system_fonts()
        _register_custom_fonts(self.fonts_dir)
        self._qr_cache: dict[str, bytes | None] = {}
        self._bg_cache_key: int | None = None
        self._bg_reader: object | None = None  # cached ImageReader for background

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_badge_pdf(
        self,
        config: dict[str, Any],
        participant_data: dict[str, Any],
        background_bytes: bytes | None = None,
        on_a4: bool = False,
    ) -> bytes:
        """Render one badge PDF page.

        Args:
            config: Template JSON config from BadgeTemplateModel.config_json
            participant_data: Keys: LAST_NAME, FIRST_NAME, MIDDLE_NAME, ROLE,
                              QR_PAYLOAD, PHOTO_BYTES, COMPETITION_NAME, INSTITUTION_NAME
            background_bytes: Raw bytes of background image, or None
            on_a4: If True the badge is centered on an A4 page instead of
                   using a badge-sized canvas. Use for single-participant
                   print-ready output.

        Returns:
            PDF as bytes (single page)
        """
        width_mm: float = float(config.get("width_mm", 90))
        height_mm: float = float(config.get("height_mm", 120))
        badge_w = width_mm * mm
        badge_h = height_mm * mm

        buf = io.BytesIO()

        if on_a4:
            from reportlab.lib.pagesizes import A4
            page_w, page_h = A4
            x_offset = (page_w - badge_w) / 2
            y_offset = (page_h - badge_h) / 2
            c = rl_canvas.Canvas(buf, pagesize=A4)
            c.saveState()
            c.translate(x_offset, y_offset)
        else:
            c = rl_canvas.Canvas(buf, pagesize=(badge_w, badge_h))

        # Background image — decode once per unique bytes object, reuse across badges
        if background_bytes:
            bg_w_mm = float(config.get("background_w_mm", width_mm))
            bg_h_mm = float(config.get("background_h_mm", height_mm))
            bg_key = id(background_bytes)
            if bg_key != self._bg_cache_key:
                self._bg_cache_key = bg_key
                self._bg_reader = None  # will be set inside _draw_image_bytes_cached
            self._draw_image_bytes_cached(
                c,
                background_bytes,
                x_rl=0,
                y_rl=0,
                w=bg_w_mm * mm,
                h=bg_h_mm * mm,
            )

        for elem in config.get("elements", []):
            self._draw_element(c, elem, participant_data, badge_h)

        if on_a4:
            c.restoreState()

        c.save()
        buf.seek(0)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _draw_element(
        self,
        c: rl_canvas.Canvas,
        elem: dict[str, Any],
        data: dict[str, Any],
        badge_h: float,
    ) -> None:
        x_mm = float(elem.get("x_mm", 0))
        y_mm = float(elem.get("y_mm", 0))
        w_mm = float(elem.get("width_mm", 20))
        h_mm = float(elem.get("height_mm", 10))

        # Flip y: JSON origin is top-left; ReportLab origin is bottom-left
        # y_rl = badge_h - (y_mm * mm) - (h_mm * mm)
        x_rl = x_mm * mm
        y_rl = badge_h - (y_mm * mm) - (h_mm * mm)
        w_rl = w_mm * mm
        h_rl = h_mm * mm

        elem_type = elem.get("type", "custom_text")

        if elem_type == "image":
            border = elem.get("border")
            radius = float(border.get("border_radius_mm", 0)) * mm if border else 0.0
            if radius > 0:
                c.saveState()
                p = _make_rounded_rect_path(c, x_rl, y_rl, w_rl, h_rl, radius)
                c.clipPath(p, stroke=0, fill=0)
                self._draw_image_element(c, elem, data, x_rl, y_rl, w_rl, h_rl)
                c.restoreState()
            else:
                self._draw_image_element(c, elem, data, x_rl, y_rl, w_rl, h_rl)
        elif elem_type == "shape":
            self._draw_shape_element(c, elem, x_rl, y_rl, w_rl, h_rl)
        else:
            # auto_text or custom_text
            text = self._resolve_text(elem, data)
            self._draw_text_element(c, elem, text, x_rl, y_rl, w_rl, h_rl)

        # Draw embedded border frame on top (for non-shape elements)
        if elem_type != "shape":
            border = elem.get("border")
            if border:
                self._draw_element_border(c, border, x_rl, y_rl, w_rl, h_rl)

    def _resolve_text(self, elem: dict, data: dict) -> str:
        elem_type = elem.get("type", "custom_text")
        if elem_type == "auto_text":
            field_key = elem.get("field_key", "")
            return str(data.get(field_key, ""))
        return str(elem.get("text", ""))

    def _draw_text_element(
        self,
        c: rl_canvas.Canvas,
        elem: dict,
        text: str,
        x_rl: float,
        y_rl: float,
        w_rl: float,
        h_rl: float,
    ) -> None:
        font_family = elem.get("font_family") or "DejaVuSans"
        font_size = float(elem.get("font_size_pt", 12))
        bold = bool(elem.get("bold", False))
        italic = bool(elem.get("italic", False))
        underline = bool(elem.get("underline", False))
        align = (elem.get("align") or "left").lower()
        hex_color = elem.get("font_color") or "#000000"

        font_name = _resolve_font(font_family, bold, italic, self.fonts_dir)
        r, g, b = _hex_to_rgb(hex_color)

        # Auto-fit: reduce font size in 0.5 pt steps until all lines fit within element height.
        # This handles multi-line role texts (e.g. "РУКОВОДИТЕЛЬ КОМАНДЫ\n(ВУЗ г.Город)")
        # that would otherwise overflow a single-line-height element.
        min_font_size = max(font_size * 0.5, 6.0)
        lines = self._wrap_text(text, font_name, font_size, w_rl)
        while font_size > min_font_size and len(lines) * font_size * 1.2 > h_rl:
            font_size -= 0.5
            lines = self._wrap_text(text, font_name, font_size, w_rl)

        c.setFont(font_name, font_size)
        c.setFillColorRGB(r, g, b)

        line_height = font_size * 1.2  # 1.2 leading

        # Start drawing from top of the element
        for i, line in enumerate(lines):
            line_y = y_rl + h_rl - (i + 1) * line_height
            if line_y < y_rl - line_height:
                break  # safety clip: should not trigger after auto-fit

            if align == "center":
                line_x = x_rl + w_rl / 2
                c.drawCentredString(line_x, line_y, line)
                if underline:
                    line_w = pdfmetrics.stringWidth(line, font_name, font_size)
                    c.line(line_x - line_w / 2, line_y - 1, line_x + line_w / 2, line_y - 1)
            elif align == "right":
                line_x = x_rl + w_rl
                c.drawRightString(line_x, line_y, line)
                if underline:
                    line_w = pdfmetrics.stringWidth(line, font_name, font_size)
                    c.line(line_x - line_w, line_y - 1, line_x, line_y - 1)
            else:  # left
                line_x = x_rl
                c.drawString(line_x, line_y, line)
                if underline:
                    line_w = pdfmetrics.stringWidth(line, font_name, font_size)
                    c.line(line_x, line_y - 1, line_x + line_w, line_y - 1)

        c.setFillColorRGB(0, 0, 0)  # reset to black

    def _draw_element_border(
        self,
        c: rl_canvas.Canvas,
        border: dict,
        x_rl: float,
        y_rl: float,
        w_rl: float,
        h_rl: float,
    ) -> None:
        """Draw a rounded-rect border frame on top of a non-shape element."""
        stroke_color = border.get("stroke_color", "#000000")
        stroke_width = float(border.get("stroke_width_pt", 1))
        border_radius_mm = float(border.get("border_radius_mm", 0))
        fill_color = border.get("fill_color", "none")
        opacity = float(border.get("opacity", 1.0))

        has_fill = bool(fill_color and fill_color != "none")
        sr, sg, sb = _hex_to_rgb(stroke_color)

        c.saveState()
        if opacity < 1.0:
            c.setFillAlpha(opacity)
            c.setStrokeAlpha(opacity)
        c.setLineWidth(stroke_width)
        c.setStrokeColorRGB(sr, sg, sb)
        if has_fill:
            fr, fg, fb = _hex_to_rgb(fill_color)
            c.setFillColorRGB(fr, fg, fb)

        do_fill = 1 if has_fill else 0
        do_stroke = 1 if stroke_width > 0 else 0
        radius = border_radius_mm * mm

        if radius > 0:
            c.roundRect(x_rl, y_rl, w_rl, h_rl, radius, fill=do_fill, stroke=do_stroke)
        else:
            c.rect(x_rl, y_rl, w_rl, h_rl, fill=do_fill, stroke=do_stroke)

        c.restoreState()

    def _draw_shape_element(
        self,
        c: rl_canvas.Canvas,
        elem: dict,
        x_rl: float,
        y_rl: float,
        w_rl: float,
        h_rl: float,
    ) -> None:
        shape_type = elem.get("shape_type", "rect")
        fill_color = elem.get("fill_color", "none")
        stroke_color = elem.get("stroke_color", "#000000")
        stroke_width = float(elem.get("stroke_width_pt", 1))
        border_radius_mm = float(elem.get("border_radius_mm", 0))
        opacity = float(elem.get("opacity", 1.0))

        # Parse fill
        has_fill = fill_color and fill_color != "none"
        if has_fill:
            fr, fg, fb = _hex_to_rgb(fill_color)
        sr, sg, sb = _hex_to_rgb(stroke_color)

        c.saveState()
        if opacity < 1.0:
            c.setFillAlpha(opacity)
            c.setStrokeAlpha(opacity)

        c.setLineWidth(stroke_width)
        if has_fill:
            c.setFillColorRGB(fr, fg, fb)
        c.setStrokeColorRGB(sr, sg, sb)

        do_fill = 1 if has_fill else 0
        do_stroke = 1 if stroke_width > 0 else 0

        if shape_type == "rect":
            from reportlab.lib.units import mm as mm_unit
            radius = border_radius_mm * mm_unit
            if radius > 0:
                c.roundRect(x_rl, y_rl, w_rl, h_rl, radius, fill=do_fill, stroke=do_stroke)
            else:
                c.rect(x_rl, y_rl, w_rl, h_rl, fill=do_fill, stroke=do_stroke)
        elif shape_type == "ellipse":
            c.ellipse(x_rl, y_rl, x_rl + w_rl, y_rl + h_rl, fill=do_fill, stroke=do_stroke)
        elif shape_type == "line":
            if do_stroke:
                c.line(x_rl, y_rl + h_rl / 2, x_rl + w_rl, y_rl + h_rl / 2)

        c.restoreState()

    def _draw_image_element(
        self,
        c: rl_canvas.Canvas,
        elem: dict,
        data: dict,
        x_rl: float,
        y_rl: float,
        w_rl: float,
        h_rl: float,
    ) -> None:
        field_key = elem.get("field_key", "")

        if field_key == "QR_IMAGE":
            qr_payload = data.get("QR_PAYLOAD", "")
            if not qr_payload:
                return
            img_bytes = self._generate_qr(qr_payload)
            if img_bytes:
                self._draw_image_bytes(c, img_bytes, x_rl, y_rl, w_rl, h_rl)

        elif field_key == "PHOTO":
            photo_bytes = data.get("PHOTO_BYTES")
            if photo_bytes:
                self._draw_image_bytes(c, photo_bytes, x_rl, y_rl, w_rl, h_rl)
            else:
                # Draw placeholder rectangle
                c.setStrokeColorRGB(0.7, 0.7, 0.7)
                c.setFillColorRGB(0.95, 0.95, 0.95)
                c.rect(x_rl, y_rl, w_rl, h_rl, fill=1)
                c.setFillColorRGB(0, 0, 0)

    def _draw_image_bytes(
        self,
        c: rl_canvas.Canvas,
        img_bytes: bytes,
        x_rl: float,
        y_rl: float,
        w: float,
        h: float,
    ) -> None:
        try:
            from PIL import Image as PILImage

            pil_img = PILImage.open(io.BytesIO(img_bytes))
            if pil_img.mode in ("RGBA", "LA") or (
                pil_img.mode == "P" and "transparency" in pil_img.info
            ):
                # Flatten transparency onto white background
                background = PILImage.new("RGB", pil_img.size, (255, 255, 255))
                if pil_img.mode == "P":
                    pil_img = pil_img.convert("RGBA")
                background.paste(pil_img, mask=pil_img.split()[-1])
                buf = io.BytesIO()
                background.save(buf, format="PNG")
                buf.seek(0)
                reader = ImageReader(buf)
            else:
                reader = ImageReader(io.BytesIO(img_bytes))
            c.drawImage(reader, x_rl, y_rl, width=w, height=h, preserveAspectRatio=False)
        except Exception as exc:
            logger.warning("Cannot draw image: %s", exc)

    def _draw_image_bytes_cached(
        self,
        c: rl_canvas.Canvas,
        img_bytes: bytes,
        x_rl: float,
        y_rl: float,
        w: float,
        h: float,
    ) -> None:
        """Like _draw_image_bytes but reuses a cached ImageReader for the same bytes object."""
        try:
            if self._bg_reader is None:
                from PIL import Image as PILImage

                pil_img = PILImage.open(io.BytesIO(img_bytes))
                if pil_img.mode in ("RGBA", "LA") or (
                    pil_img.mode == "P" and "transparency" in pil_img.info
                ):
                    background = PILImage.new("RGB", pil_img.size, (255, 255, 255))
                    if pil_img.mode == "P":
                        pil_img = pil_img.convert("RGBA")
                    background.paste(pil_img, mask=pil_img.split()[-1])
                    buf = io.BytesIO()
                    background.save(buf, format="PNG")
                    buf.seek(0)
                    self._bg_reader = ImageReader(buf)
                else:
                    self._bg_reader = ImageReader(io.BytesIO(img_bytes))
            c.drawImage(self._bg_reader, x_rl, y_rl, width=w, height=h, preserveAspectRatio=False)
        except Exception as exc:
            logger.warning("Cannot draw cached background image: %s", exc)

    def _generate_qr(self, payload: str) -> bytes | None:
        if payload in self._qr_cache:
            return self._qr_cache[payload]
        try:
            from ...domain.services import QRService
            result = QRService().generate_qr_code(payload, error_correction="H", box_size=6, border=1)
        except Exception as exc:
            logger.warning("QR generation failed: %s", exc)
            result = None
        self._qr_cache[payload] = result
        return result

    @staticmethod
    def _wrap_text(text: str, font_name: str, font_size: float, max_width: float) -> list[str]:
        """Word-wrap text to fit within max_width, honouring explicit \\n line breaks."""
        if not text:
            return [""]
        result_lines: list[str] = []
        for paragraph in text.split("\n"):
            if not paragraph.strip():
                result_lines.append("")
                continue
            words = paragraph.split()
            lines: list[str] = []
            current = ""
            for word in words:
                candidate = f"{current} {word}".strip() if current else word
                if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
                    current = candidate
                else:
                    if current:
                        lines.append(current)
                    # If a single word is too long, just add it as-is
                    current = word
            if current:
                lines.append(current)
            result_lines.extend(lines or [""])
        return result_lines or [""]
