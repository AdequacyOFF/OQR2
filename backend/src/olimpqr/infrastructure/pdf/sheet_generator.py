"""Answer sheet PDF generator with QR code."""

from io import BytesIO
import json
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from ...domain.services import QRService
from ...config import settings


# Register fonts with Cyrillic support
# Liberation Serif is a formal serif font (Times New Roman equivalent) suitable for olympiad documents
import os

_FONT_REGISTERED = False
_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"

def _register_fonts():
    """Register Liberation Serif fonts for formal olympiad documents."""
    global _FONT_REGISTERED, _FONT_REGULAR, _FONT_BOLD

    if _FONT_REGISTERED:
        return

    try:
        # Liberation Serif - formal serif font for official documents
        liberation_path = '/usr/share/fonts/truetype/liberation/'
        if os.path.exists(liberation_path + 'LiberationSerif-Regular.ttf'):
            pdfmetrics.registerFont(TTFont('LiberationSerif', liberation_path + 'LiberationSerif-Regular.ttf'))
            pdfmetrics.registerFont(TTFont('LiberationSerif-Bold', liberation_path + 'LiberationSerif-Bold.ttf'))
            _FONT_REGULAR = "LiberationSerif"
            _FONT_BOLD = "LiberationSerif-Bold"
            _FONT_REGISTERED = True
            return
    except Exception as e:
        print(f"Warning: Could not register Liberation Serif fonts: {e}")

    try:
        # Fallback to DejaVu Sans (sans-serif but has good Cyrillic support)
        dejavu_path = '/usr/share/fonts/truetype/dejavu/'
        if os.path.exists(dejavu_path + 'DejaVuSans.ttf'):
            pdfmetrics.registerFont(TTFont('DejaVuSans', dejavu_path + 'DejaVuSans.ttf'))
            pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', dejavu_path + 'DejaVuSans-Bold.ttf'))
            _FONT_REGULAR = "DejaVuSans"
            _FONT_BOLD = "DejaVuSans-Bold"
            _FONT_REGISTERED = True
            return
    except Exception as e:
        print(f"Warning: Could not register DejaVu fonts: {e}")

    # Final fallback is Helvetica (already set as default)
    _FONT_REGISTERED = True

# Register fonts on module load
_register_fonts()


class SheetGenerator:
    """Generator for answer sheet PDFs with QR codes."""

    def __init__(self):
        self.qr_service = QRService()
        self.page_width, self.page_height = A4
        self.template_overrides = self._load_template_overrides()

    def _load_template_overrides(self) -> dict:
        """Load optional JSON template for easy non-code customization."""
        candidate_paths: list[str] = []
        if settings.sheet_template_path:
            candidate_paths.append(settings.sheet_template_path)

        candidate_paths.append(os.path.join(os.path.dirname(__file__), "sheet_template.json"))
        candidate_paths.append(os.path.join(os.path.dirname(__file__), "sheet_template.override.json"))

        for path in candidate_paths:
            if not path:
                continue
            if not os.path.exists(path):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                print(f"Warning: could not load sheet template {path}: {e}")
        return {}

    def _template_value(self, key: str, default):
        value = self.template_overrides.get(key, default)
        return value

    def generate_answer_sheet(
        self,
        competition_name: str,
        variant_number: int,
        sheet_token: str
    ) -> bytes:
        """Generate answer sheet PDF with QR code.

        Args:
            competition_name: Name of the competition
            variant_number: Test variant number
            sheet_token: Token for QR code (for linking scan to attempt)

        Returns:
            PDF file as bytes
        """
        # Create PDF in memory
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)

        # Draw logo in top left corner
        self._draw_logo(c)

        # Draw header
        self._draw_header(c, competition_name, variant_number)

        # Draw QR code
        self._draw_qr_code(c, sheet_token)

        # Draw score field (fixed position for OCR)
        self._draw_score_field(c)

        # Draw answer fields
        self._draw_answer_fields(c)

        # Draw footer
        self._draw_footer(c)

        # Finalize PDF
        c.save()

        # Get PDF bytes
        buffer.seek(0)
        return buffer.getvalue()

    def _draw_logo(self, c: canvas.Canvas):
        """Draw logo in top left corner."""
        import os
        if not self._template_value("show_logo", True):
            return
        logo_path = os.path.join(os.path.dirname(__file__), 'logo_black.png')

        if os.path.exists(logo_path):
            try:
                logo_image = ImageReader(logo_path)
                # Draw logo (30mm x 30mm in top left)
                logo_x = 15*mm
                logo_y = self.page_height - 35*mm
                logo_size = 25*mm

                c.drawImage(
                    logo_image,
                    logo_x,
                    logo_y,
                    width=logo_size,
                    height=logo_size,
                    preserveAspectRatio=True,
                    mask='auto'
                )
            except Exception as e:
                # If logo fails to load, continue without it
                print(f"Warning: Could not load logo: {e}")

    def _draw_header(
        self,
        c: canvas.Canvas,
        competition_name: str,
        variant_number: int
    ):
        """Draw header with competition info.

        Note: variant_number parameter is kept for API compatibility but not rendered.
        """
        # Use formal serif font (Liberation Serif) for olympiad documents
        c.setFont(_FONT_BOLD, 18)
        c.drawCentredString(
            self.page_width / 2,
            self.page_height - 30*mm,
            self._template_value("title", "БЛАНК ОТВЕТОВ")
        )
        # Variant number intentionally not displayed per requirement

    def _draw_qr_code(self, c: canvas.Canvas, sheet_token: str):
        """Draw QR code in top right corner."""
        # Generate QR code
        qr_bytes = self.qr_service.generate_qr_code(
            sheet_token,
            error_correction=settings.qr_error_correction,
            box_size=8,
            border=2
        )

        # Save QR to temp buffer and wrap with ImageReader
        qr_buffer = BytesIO(qr_bytes)
        qr_image = ImageReader(qr_buffer)

        # Draw QR code (40mm x 40mm in top right)
        qr_x = self.page_width - 50*mm
        qr_y = self.page_height - 50*mm
        qr_size = 40*mm

        c.drawImage(
            qr_image,
            qr_x,
            qr_y,
            width=qr_size,
            height=qr_size,
            preserveAspectRatio=True
        )

        # Draw label
        c.setFont("Helvetica", 8)
        c.drawString(qr_x, qr_y - 5*mm, "QR-код")

    def _get_answer_frame_geometry(self):
        """Get answer frame geometry (shared between answer fields and score field).

        Returns:
            tuple: (frame_x, frame_y, frame_width, frame_height) in ReportLab units
        """
        frame_x = 20*mm
        frame_y = self.page_height - 240*mm - 20*mm
        frame_width = self.page_width - 40*mm
        frame_height = 165*mm + 20*mm
        return frame_x, frame_y, frame_width, frame_height

    def _draw_score_field(self, c: canvas.Canvas):
        """Draw score field in bottom-right corner of answer frame for OCR.

        Position: 13mm from bottom edge of the sheet, right-aligned in the frame.

        CRITICAL: These coordinates must match OCR settings!
        Update config.py defaults if frame geometry changes.
        """
        # Get answer frame geometry
        frame_x, frame_y, frame_width, frame_height = self._get_answer_frame_geometry()

        # Score box dimensions
        width = settings.ocr_score_field_width * mm
        height = settings.ocr_score_field_height * mm

        # X position: right-aligned with 10mm margin from frame right edge
        margin = 10*mm
        x = frame_x + frame_width - margin - width

        # Y position: 13mm from bottom edge of the sheet
        y = 13*mm

        # Draw thick border for OCR detection
        c.setStrokeColor(colors.black)
        c.setLineWidth(2)
        c.rect(x, y, width, height)

        # Draw label with formal serif font (right-aligned above the box)
        c.setFont(_FONT_BOLD, 10)
        c.drawRightString(x + width, y + height + 3*mm, "ИТОГОВЫЙ БАЛЛ:")

        # Draw instruction (right-aligned below the box)
        c.setFont(_FONT_REGULAR, 8)
        c.drawRightString(
            x + width,
            y - 5*mm,
            "Напишите итоговый балл ПЕЧАТНЫМИ цифрами"
        )

        # Draw placeholder
        c.setFont("Courier-Bold", 24)
        c.setFillColor(colors.lightgrey)
        c.drawCentredString(
            x + width/2,
            y + 3*mm,
            "___"
        )
        c.setFillColor(colors.black)

    def _draw_answer_fields(self, c: canvas.Canvas):
        """Draw large answer grid with notebook-style grid."""
        # Warning text with formal serif font
        c.setFont(_FONT_BOLD, 11)
        c.setFillColor(colors.red)
        warning_y = self.page_height - 60*mm
        c.drawCentredString(
            self.page_width / 2,
            warning_y,
            self._template_value("warning_text", "ВНИМАНИЕ! Заполняйте ответы строго внутри рамки")
        )
        c.setFillColor(colors.black)

        # Get frame geometry from shared method
        frame_x, frame_y, frame_width, frame_height = self._get_answer_frame_geometry()

        # Draw thick outer border
        c.setStrokeColor(colors.black)
        c.setLineWidth(2)
        c.rect(frame_x, frame_y, frame_width, frame_height)

        # Draw horizontal grid lines
        c.setLineWidth(0.5)
        c.setStrokeColor(colors.HexColor("#CCCCCC"))
        line_spacing = 10*mm  # Increased from 8mm for better handwriting space
        num_h_lines = int(frame_height / line_spacing)

        for i in range(1, num_h_lines):
            y = frame_y + (i * line_spacing)
            c.line(frame_x, y, frame_x + frame_width, y)

        # Draw vertical grid lines for proper grid
        col_spacing = 10*mm  # Increased from 8mm for better handwriting space
        num_v_lines = int(frame_width / col_spacing)

        for i in range(1, num_v_lines):
            x = frame_x + (i * col_spacing)
            c.line(x, frame_y, x, frame_y + frame_height)

        c.setStrokeColor(colors.black)

    def _draw_footer(self, c: canvas.Canvas):
        """Draw footer with instructions (no signature field)."""
        c.setFont(_FONT_REGULAR, 8)
        c.setFillColor(colors.grey)

        footer_text = self._template_value("footer_lines", [
            "Инструкции:",
            "1. Отвечайте четко и разборчиво",
            "2. Укажите итоговый балл в специальном поле",
            "3. Не сгибайте и не пачкайте лист"
        ])

        y = 30*mm
        for line in footer_text:
            c.drawString(20*mm, y, line)
            y -= 4*mm

        c.setFillColor(colors.black)
