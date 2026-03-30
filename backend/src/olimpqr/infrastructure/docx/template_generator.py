"""DOCX template generator for special olympiad documents."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.shared import Mm, Pt

from ...config import settings
from ...domain.services import QRService


@dataclass
class TourConfig:
    """Single tour configuration used for document generation."""

    tour_number: int
    mode: str
    task_numbers: list[int]


class WordTemplateGenerator:
    """Generate DOCX files from editable Word templates."""

    ANSWER_TEMPLATE_NAME = "special_answer_blank_template.docx"
    A3_COVER_TEMPLATE_NAME = "special_cover_a3_template.docx"

    def __init__(self, templates_dir: str | None = None):
        base_path = (
            Path(templates_dir)
            if templates_dir
            else Path(__file__).resolve().parents[4] / "templates" / "word"
        )
        self.templates_dir = base_path
        self.answer_template_path = self.templates_dir / self.ANSWER_TEMPLATE_NAME
        self.a3_cover_template_path = self.templates_dir / self.A3_COVER_TEMPLATE_NAME
        self.qr_service = QRService()

    def ensure_templates_exist(self) -> None:
        """Create default templates if missing."""
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        if not self.answer_template_path.exists():
            self._create_default_answer_template(self.answer_template_path)
        if not self.a3_cover_template_path.exists():
            self._create_default_a3_cover_template(self.a3_cover_template_path)

    def get_template_paths(self) -> dict[str, str]:
        self.ensure_templates_exist()
        return {
            "answer_blank": str(self.answer_template_path),
            "a3_cover": str(self.a3_cover_template_path),
        }

    def generate_answer_blank(
        self,
        qr_payload: str,
        tour_number: int,
        task_number: int,
        mode: str,
    ) -> bytes:
        """Render answer blank DOCX from template."""
        self.ensure_templates_exist()
        doc = Document(str(self.answer_template_path))
        self._replace_text_tokens(
            doc,
            {
                "{{TOUR_NUMBER}}": str(tour_number),
                "{{TASK_NUMBER}}": str(task_number),
                "{{TOUR_MODE}}": mode,
                "{{TOUR_TASK}}": f"{tour_number}/{task_number}",
            },
        )
        qr_bytes = self._build_qr_png(qr_payload)
        self._replace_qr_token(doc, "{{QR_IMAGE}}", qr_bytes, width_mm=35)
        return self._save_doc_to_bytes(doc)

    def generate_a3_cover(
        self,
        qr_payload: str,
        tour_number: int,
        mode: str,
    ) -> bytes:
        """Render A3 cover DOCX from template."""
        self.ensure_templates_exist()
        doc = Document(str(self.a3_cover_template_path))
        self._replace_text_tokens(
            doc,
            {
                "{{TOUR_NUMBER}}": str(tour_number),
                "{{TOUR_MODE}}": mode,
            },
        )
        qr_bytes = self._build_qr_png(qr_payload)
        self._replace_qr_token(doc, "{{QR_IMAGE}}", qr_bytes, width_mm=45)
        return self._save_doc_to_bytes(doc)

    def _build_qr_png(self, payload: str) -> bytes:
        return self.qr_service.generate_qr_code(
            payload,
            error_correction=settings.qr_error_correction,
            box_size=8,
            border=2,
        )

    def _replace_text_tokens(self, doc: Document, mapping: dict[str, str]) -> None:
        for paragraph in self._iter_all_paragraphs(doc):
            self._replace_text_tokens_in_paragraph(paragraph, mapping)

    def _replace_qr_token(self, doc: Document, token: str, qr_png: bytes, width_mm: float = 35) -> None:
        for paragraph in self._iter_all_paragraphs(doc):
            if token in paragraph.text:
                self._insert_qr_in_paragraph(paragraph, token=token, qr_png=qr_png, width_mm=width_mm)
                return

        # Fallback: append QR at the end if token not found.
        paragraph = doc.add_paragraph()
        run = paragraph.add_run()
        run.add_picture(io.BytesIO(qr_png), width=Mm(width_mm))

    def _iter_all_paragraphs(self, doc: Document) -> Iterable:
        yield from doc.paragraphs
        for table in doc.tables:
            yield from self._iter_table_paragraphs(table)

        # Also support tokens in headers/footers.
        for section in doc.sections:
            for part in (section.header, section.footer):
                yield from part.paragraphs
                for table in part.tables:
                    yield from self._iter_table_paragraphs(table)

    def _iter_table_paragraphs(self, table) -> Iterable:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs
                for nested_table in cell.tables:
                    yield from self._iter_table_paragraphs(nested_table)

    def _replace_text_tokens_in_paragraph(self, paragraph, mapping: dict[str, str]) -> None:
        if not paragraph.text:
            return

        # Fast path: replace inside runs to keep user styling intact.
        run_updated = False
        for run in paragraph.runs:
            original = run.text
            replaced = original
            for token, value in mapping.items():
                replaced = replaced.replace(token, value)
            if replaced != original:
                run.text = replaced
                run_updated = True

        if run_updated:
            return

        # Fallback when token is split across multiple runs.
        original = paragraph.text
        replaced = original
        for token, value in mapping.items():
            replaced = replaced.replace(token, value)
        if replaced == original:
            return

        if paragraph.runs:
            paragraph.runs[0].text = replaced
            for run in paragraph.runs[1:]:
                run.text = ""
        else:
            paragraph.text = replaced

    @staticmethod
    def _insert_qr_in_paragraph(paragraph, token: str, qr_png: bytes, width_mm: float) -> None:
        text = paragraph.text
        before, after = text.split(token, 1)

        if paragraph.runs:
            paragraph.runs[0].text = before
            for run in paragraph.runs[1:]:
                run.text = ""
        else:
            paragraph.add_run(before)

        qr_run = paragraph.add_run()
        qr_run.add_picture(io.BytesIO(qr_png), width=Mm(width_mm))
        if after:
            paragraph.add_run(after)

    @staticmethod
    def _save_doc_to_bytes(doc: Document) -> bytes:
        stream = io.BytesIO()
        doc.save(stream)
        stream.seek(0)
        return stream.read()

    @staticmethod
    def _create_default_answer_template(path: Path) -> None:
        doc = Document()
        title = doc.add_heading("ANSWER BLANK", level=1)
        title.alignment = 1

        p = doc.add_paragraph()
        p.add_run("Tour: ").bold = True
        p.add_run("{{TOUR_NUMBER}}")
        p.add_run("    ")
        p.add_run("Task: ").bold = True
        p.add_run("{{TASK_NUMBER}}")

        p2 = doc.add_paragraph()
        p2.add_run("Mode: ").bold = True
        p2.add_run("{{TOUR_MODE}}")
        p2.add_run("    ")
        p2.add_run("Code: ").bold = True
        p2.add_run("{{TOUR_TASK}}")

        doc.add_paragraph("QR: {{QR_IMAGE}}")

        doc.add_paragraph("Participant name: ______________________________")
        doc.add_paragraph("Institution: ______________________________")
        doc.add_paragraph("Answer:")

        answer_box = doc.add_table(rows=12, cols=1)
        for row in answer_box.rows:
            row.height = Mm(12)

        foot = doc.add_paragraph(
            "This template is editable in Word. Keep tokens: {{QR_IMAGE}}, {{TOUR_NUMBER}}, {{TASK_NUMBER}}, {{TOUR_MODE}}, {{TOUR_TASK}}."
        )
        for run in foot.runs:
            run.font.size = Pt(9)

        doc.save(str(path))

    @staticmethod
    def _create_default_a3_cover_template(path: Path) -> None:
        doc = Document()
        section = doc.sections[0]
        section.page_width = Mm(420)
        section.page_height = Mm(297)
        section.left_margin = Mm(10)
        section.right_margin = Mm(10)
        section.top_margin = Mm(10)
        section.bottom_margin = Mm(10)

        heading = doc.add_paragraph("A3 BOOKLET COVER (landscape)")
        heading.runs[0].bold = True
        heading.runs[0].font.size = Pt(16)
        heading.alignment = 1

        hint = doc.add_paragraph("Fold by center line: left side becomes inner page, right side becomes outer cover.")
        hint.runs[0].font.size = Pt(9)
        hint.alignment = 1

        layout = doc.add_table(rows=1, cols=2)
        layout.autofit = False
        for row in layout.rows:
            row.height = Mm(235)
        left_cell, right_cell = layout.rows[0].cells
        left_cell.width = Mm(195)
        right_cell.width = Mm(195)

        # Inner side (left half)
        p = left_cell.paragraphs[0]
        p.add_run("INNER SIDE").bold = True
        p.runs[0].font.size = Pt(12)
        left_cell.add_paragraph("Participant full name (handwritten): __________________________________")
        left_cell.add_paragraph("Institution (handwritten): __________________________________")
        left_cell.add_paragraph("Team / branch (optional): __________________________________")
        left_cell.add_paragraph("Start time: _____________   End time: _____________")
        left_cell.add_paragraph("Invigilator signature: ____________________________")
        left_cell.add_paragraph(" ")
        left_cell.add_paragraph("Contents checklist:")
        left_cell.add_paragraph("1) Answer sheets for this tour")
        left_cell.add_paragraph("2) Additional sheets if issued")

        # Outer cover (right half)
        p = right_cell.paragraphs[0]
        p.add_run("OUTER COVER").bold = True
        p.runs[0].font.size = Pt(12)
        meta = right_cell.add_paragraph()
        meta.add_run("Tour: ").bold = True
        meta.add_run("{{TOUR_NUMBER}}")
        meta.add_run("   ")
        meta.add_run("Mode: ").bold = True
        meta.add_run("{{TOUR_MODE}}")
        right_cell.add_paragraph("Participant full name (handwritten): __________________________________")
        right_cell.add_paragraph("Institution (handwritten): __________________________________")
        right_cell.add_paragraph("Start time: _____________   End time: _____________")
        right_cell.add_paragraph("QR: {{QR_IMAGE}}")
        right_cell.add_paragraph("Keep tokens: {{QR_IMAGE}}, {{TOUR_NUMBER}}, {{TOUR_MODE}}.")

        doc.save(str(path))

