"""Compose grouped A4 badge PDF from single-badge PDF pages."""

from __future__ import annotations

from dataclasses import dataclass

import fitz


@dataclass
class TemplateBadgePdfItem:
    """Single badge PDF page plus grouping metadata."""

    institution: str
    pdf_bytes: bytes


class BadgeTemplatePdfGenerator:
    """Place converted badge PDFs on A4 pages grouped by institution."""

    COLS = 2
    ROWS = 2
    BADGES_PER_PAGE = 4

    MARGIN_X_MM = 10.0
    MARGIN_Y_MM = 10.0
    BADGE_W_MM = 90.0
    BADGE_H_MM = 120.0
    HEADER_OFFSET_MM = 15.0

    @staticmethod
    def _mm_to_pt(value_mm: float) -> float:
        return value_mm * 72.0 / 25.4

    def generate_grouped_pdf(
        self,
        competition_name: str,
        items: list[TemplateBadgePdfItem],
    ) -> bytes:
        groups: dict[str, list[TemplateBadgePdfItem]] = {}
        for item in items:
            key = item.institution or "Без учреждения"
            groups.setdefault(key, []).append(item)

        page_rect = fitz.paper_rect("a4")
        page_w = page_rect.width
        page_h = page_rect.height

        margin_x = self._mm_to_pt(self.MARGIN_X_MM)
        margin_y = self._mm_to_pt(self.MARGIN_Y_MM)
        badge_w = self._mm_to_pt(self.BADGE_W_MM)
        badge_h = self._mm_to_pt(self.BADGE_H_MM)
        header_offset = self._mm_to_pt(self.HEADER_OFFSET_MM)
        gap_x = max((page_w - 2 * margin_x - (self.COLS * badge_w)) / max(self.COLS - 1, 1), 0)
        gap_y = max(
            (page_h - 2 * margin_y - header_offset - (self.ROWS * badge_h)) / max(self.ROWS - 1, 1),
            0,
        )

        out_doc = fitz.open()
        for institution in sorted(groups.keys()):
            institution_items = groups[institution]
            badge_index = 0
            page = None

            for badge in institution_items:
                if badge_index % self.BADGES_PER_PAGE == 0:
                    page = out_doc.new_page(width=page_w, height=page_h)
                    self._draw_header(page, competition_name, institution, page_w, margin_y)

                slot = badge_index % self.BADGES_PER_PAGE
                col = slot % self.COLS
                row = slot // self.COLS
                x = margin_x + col * (badge_w + gap_x)
                y = page_h - margin_y - header_offset - (row + 1) * badge_h - row * gap_y
                rect = fitz.Rect(x, y, x + badge_w, y + badge_h)

                with fitz.open(stream=badge.pdf_bytes, filetype="pdf") as badge_doc:
                    if badge_doc.page_count > 0 and page is not None:
                        page.show_pdf_page(rect, badge_doc, 0)

                badge_index += 1

        if out_doc.page_count == 0:
            out_doc.new_page(width=page_w, height=page_h)

        try:
            return out_doc.tobytes(garbage=4, deflate=True)
        finally:
            out_doc.close()

    @staticmethod
    def _draw_header(page, competition_name: str, institution: str, page_w: float, margin_y: float) -> None:
        title = f"{competition_name} — {institution}"
        rect = fitz.Rect(0, margin_y * 0.2, page_w, margin_y + 25)
        font_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
        for font_path in font_candidates:
            try:
                page.insert_textbox(
                    rect,
                    title,
                    fontsize=11,
                    fontfile=font_path,
                    align=1,
                )
                return
            except Exception:  # noqa: BLE001
                continue

        page.insert_textbox(rect, title, fontsize=11, align=1)
