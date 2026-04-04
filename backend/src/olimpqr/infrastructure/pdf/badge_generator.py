"""Badge PDF generator for participant QR badges."""

from dataclasses import dataclass
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics

from ...domain.services import QRService
from .sheet_generator import _register_fonts, _FONT_REGULAR, _FONT_BOLD


@dataclass
class BadgeData:
    """Data for a single badge."""
    name: str
    school: str
    institution: str
    qr_token: str


class BadgeGenerator:
    """Generator for participant badge PDFs with QR codes."""

    # Badge dimensions (fixed 90x120 mm, 2x2 grid on A4)
    COLS = 2
    ROWS = 2
    BADGES_PER_PAGE = 4

    # A4 page
    PAGE_W, PAGE_H = A4

    # Margins
    MARGIN_X = 10 * mm
    MARGIN_Y = 10 * mm

    # Badge size (required)
    BADGE_W = 90 * mm
    BADGE_H = 120 * mm

    # Header area and spacing in the page grid
    HEADER_OFFSET = 15 * mm
    GAP_X = max((PAGE_W - 2 * MARGIN_X - (COLS * BADGE_W)) / max(COLS - 1, 1), 0)
    GAP_Y = max((PAGE_H - 2 * MARGIN_Y - HEADER_OFFSET - (ROWS * BADGE_H)) / max(ROWS - 1, 1), 0)

    # QR size inside badge
    QR_SIZE = 38 * mm

    # Typography
    TITLE_FONT_SIZE = 13
    COMP_FONT_SIZE = 8
    NAME_FONT_SIZE = 12
    SCHOOL_FONT_SIZE = 8
    HINT_FONT_SIZE = 7

    def __init__(self):
        _register_fonts()
        self.qr_service = QRService()

    def generate_badges_pdf(
        self,
        competition_name: str,
        badges: list[BadgeData],
    ) -> bytes:
        """Generate a PDF with badges grouped by institution.

        Args:
            competition_name: Name of the competition
            badges: List of badge data, pre-sorted by institution then name

        Returns:
            PDF file as bytes
        """
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)

        # Group badges by institution
        groups: dict[str, list[BadgeData]] = {}
        for badge in badges:
            key = badge.institution or "Без учреждения"
            groups.setdefault(key, []).append(badge)

        # Sort groups alphabetically
        sorted_institutions = sorted(groups.keys())

        badge_index = 0  # position on current page (0..3)
        first_page = True

        for institution in sorted_institutions:
            group_badges = groups[institution]

            # Start new page for each institution group
            if not first_page:
                c.showPage()
                badge_index = 0
            first_page = False

            # Draw institution header at top of page
            self._draw_institution_header(c, institution, competition_name)

            for badge in group_badges:
                if badge_index >= self.BADGES_PER_PAGE:
                    c.showPage()
                    badge_index = 0
                    self._draw_institution_header(c, institution, competition_name)

                col = badge_index % self.COLS
                row = badge_index // self.COLS

                # Badge origin (bottom-left corner)
                x = self.MARGIN_X + col * (self.BADGE_W + self.GAP_X)
                # Offset rows down to leave room for header
                y = self.PAGE_H - self.MARGIN_Y - self.HEADER_OFFSET - (row + 1) * self.BADGE_H - row * self.GAP_Y

                self._draw_badge(c, x, y, badge, competition_name)
                badge_index += 1

        c.save()
        buffer.seek(0)
        return buffer.getvalue()

    def _draw_institution_header(
        self, c: canvas.Canvas, institution: str, competition_name: str
    ):
        """Draw institution name header at top of page."""
        c.setFont(_FONT_BOLD, 11)
        c.drawCentredString(
            self.PAGE_W / 2,
            self.PAGE_H - self.MARGIN_Y - 5 * mm,
            f"{competition_name} — {institution}",
        )

    @staticmethod
    def _line_height_mm(font_size_pt: float) -> float:
        # 1pt = 0.352778 mm, with ~1.2 line spacing
        return font_size_pt * 0.352778 * 1.2

    @staticmethod
    def _fit_text_lines(
        text: str,
        font_name: str,
        font_size: float,
        max_width: float,
        max_lines: int,
    ) -> list[str]:
        text = (text or "").strip()
        if not text:
            return [""]

        words = text.split()
        lines: list[str] = []
        current = ""

        def _width(value: str) -> float:
            return pdfmetrics.stringWidth(value, font_name, font_size)

        for word in words:
            candidate = f"{current} {word}".strip()
            if not current or _width(candidate) <= max_width:
                current = candidate
                continue
            lines.append(current)
            current = word
            if len(lines) == max_lines:
                break

        if len(lines) < max_lines and current:
            lines.append(current)

        if not lines:
            lines = [text]

        # Fallback for long tokens without spaces and final clamp.
        for i, line in enumerate(lines):
            if _width(line) <= max_width:
                continue
            trimmed = line
            while len(trimmed) > 1 and _width(trimmed + "...") > max_width:
                trimmed = trimmed[:-1]
            lines[i] = trimmed + ("..." if trimmed != line else "")

        if len(lines) > max_lines:
            lines = lines[:max_lines]

        return lines

    def _draw_badge(
        self,
        c: canvas.Canvas,
        x: float,
        y: float,
        badge: BadgeData,
        competition_name: str,
    ):
        """Draw a single badge at the given position."""
        w = self.BADGE_W
        h = self.BADGE_H
        pad = 4 * mm
        content_w = w - 2 * pad
        content_h = h - 2 * pad

        # Dashed cut-line border
        c.setStrokeColor(colors.grey)
        c.setLineWidth(0.5)
        c.setDash(3, 3)
        c.rect(x, y, w, h)
        c.setDash()  # reset

        import os

        logo_path = os.path.join(os.path.dirname(__file__), "logo_black.png")
        logo_size = 16 * mm
        logo_image = None
        if os.path.exists(logo_path):
            try:
                logo_image = ImageReader(logo_path)
            except Exception:
                logo_image = None

        comp_lines = self._fit_text_lines(
            text=competition_name,
            font_name=_FONT_REGULAR,
            font_size=self.COMP_FONT_SIZE,
            max_width=content_w,
            max_lines=2,
        )
        name_lines = self._fit_text_lines(
            text=badge.name,
            font_name=_FONT_BOLD,
            font_size=self.NAME_FONT_SIZE,
            max_width=content_w,
            max_lines=2,
        )
        school_lines = self._fit_text_lines(
            text=badge.school,
            font_name=_FONT_REGULAR,
            font_size=self.SCHOOL_FONT_SIZE,
            max_width=content_w,
            max_lines=2,
        )

        title_h = self._line_height_mm(self.TITLE_FONT_SIZE)
        comp_h = len(comp_lines) * self._line_height_mm(self.COMP_FONT_SIZE)
        name_h = len(name_lines) * self._line_height_mm(self.NAME_FONT_SIZE)
        school_h = len(school_lines) * self._line_height_mm(self.SCHOOL_FONT_SIZE)
        hint_h = self._line_height_mm(self.HINT_FONT_SIZE)
        logo_h = logo_size if logo_image is not None else 0

        gap = 2.2 * mm
        parts_count = 6 if logo_image is not None else 5
        block_h = logo_h + title_h + comp_h + name_h + school_h + self.QR_SIZE + hint_h + gap * (parts_count - 1)

        cx = x + w / 2
        top = y + pad + (content_h + block_h) / 2

        if logo_image is not None:
            c.drawImage(
                logo_image,
                cx - logo_size / 2,
                top - logo_size,
                width=logo_size,
                height=logo_size,
                preserveAspectRatio=True,
                mask="auto",
            )
            top -= logo_size + gap

        c.setFont(_FONT_BOLD, self.TITLE_FONT_SIZE)
        title_baseline = top - title_h + (title_h - self.TITLE_FONT_SIZE * 0.352778) / 2
        c.drawCentredString(cx, title_baseline, "OlimpQR")
        top -= title_h + gap

        c.setFont(_FONT_REGULAR, self.COMP_FONT_SIZE)
        comp_line_h = self._line_height_mm(self.COMP_FONT_SIZE)
        for line in comp_lines:
            baseline = top - comp_line_h + (comp_line_h - self.COMP_FONT_SIZE * 0.352778) / 2
            c.drawCentredString(cx, baseline, line)
            top -= comp_line_h
        top -= gap

        c.setFont(_FONT_BOLD, self.NAME_FONT_SIZE)
        name_line_h = self._line_height_mm(self.NAME_FONT_SIZE)
        for line in name_lines:
            baseline = top - name_line_h + (name_line_h - self.NAME_FONT_SIZE * 0.352778) / 2
            c.drawCentredString(cx, baseline, line)
            top -= name_line_h
        top -= gap

        c.setFont(_FONT_REGULAR, self.SCHOOL_FONT_SIZE)
        school_line_h = self._line_height_mm(self.SCHOOL_FONT_SIZE)
        for line in school_lines:
            baseline = top - school_line_h + (school_line_h - self.SCHOOL_FONT_SIZE * 0.352778) / 2
            c.drawCentredString(cx, baseline, line)
            top -= school_line_h
        top -= gap

        # QR code (centered)
        qr_bytes = self.qr_service.generate_qr_code(
            badge.qr_token, error_correction="H", box_size=6, border=1
        )
        qr_buffer = BytesIO(qr_bytes)
        qr_image = ImageReader(qr_buffer)
        qr_x = cx - self.QR_SIZE / 2
        qr_y = top - self.QR_SIZE
        c.drawImage(
            qr_image,
            qr_x,
            qr_y,
            width=self.QR_SIZE,
            height=self.QR_SIZE,
            preserveAspectRatio=True,
        )
        top = qr_y - gap

        # Hint text below QR
        c.setFont(_FONT_REGULAR, self.HINT_FONT_SIZE)
        c.setFillColor(colors.grey)
        hint_line_h = self._line_height_mm(self.HINT_FONT_SIZE)
        hint_baseline = top - hint_line_h + (hint_line_h - self.HINT_FONT_SIZE * 0.352778) / 2
        c.drawCentredString(cx, hint_baseline, "Show QR code for admission")
        c.setFillColor(colors.black)
