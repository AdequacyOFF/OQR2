"""DOCX template generator for special olympiad documents."""

from __future__ import annotations

import concurrent.futures
import io
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.shared import Mm, Pt
from PIL import Image, ImageOps

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
    BADGE_TEMPLATE_NAME = "badge_template.docx"
    BADGE_PHOTOS_DIR_NAME = "badge_photos"
    BADGE_PHOTO_DPI = 220
    DOCX_TO_PDF_BATCH_SIZE = 10
    DOCX_TO_PDF_TIMEOUT_SEC = 300
    # Max parallel soffice workers. Each gets its own tmpdir/lo_profile.
    DOCX_TO_PDF_MAX_WORKERS = 4
    # Conservative per-file timeout budget (seconds). Actual batch timeout =
    # max(DOCX_TO_PDF_TIMEOUT_SEC, batch_size * DOCX_TO_PDF_SEC_PER_FILE).
    DOCX_TO_PDF_SEC_PER_FILE = 45

    # Track which OS process has already installed custom fonts system-wide.
    # Resets naturally on Docker restart (new PID), triggering reinstall.
    _system_fonts_pid: int = 0

    def __init__(self, templates_dir: str | None = None):
        base_path = (
            Path(templates_dir)
            if templates_dir
            else Path(__file__).resolve().parents[4] / "templates" / "word"
        )
        self.templates_dir = base_path
        self.answer_template_path = self.templates_dir / self.ANSWER_TEMPLATE_NAME
        self.a3_cover_template_path = self.templates_dir / self.A3_COVER_TEMPLATE_NAME
        self.badge_template_path = self.templates_dir / self.BADGE_TEMPLATE_NAME
        self.badge_photos_dir = self.templates_dir / self.BADGE_PHOTOS_DIR_NAME
        self.fonts_dir = self.templates_dir / "fonts"
        self.qr_service = QRService()
        self._badge_photo_index: dict[str, Path] | None = None

    def ensure_templates_exist(self) -> None:
        """Create default templates if missing."""
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        if not self.answer_template_path.exists():
            self._create_default_answer_template(self.answer_template_path)
        if not self.a3_cover_template_path.exists():
            self._create_default_a3_cover_template(self.a3_cover_template_path)
        if not self.badge_template_path.exists():
            self._create_default_badge_template(self.badge_template_path)
        self.badge_photos_dir.mkdir(parents=True, exist_ok=True)
        self.fonts_dir.mkdir(parents=True, exist_ok=True)

    def get_template_paths(self) -> dict[str, str]:
        self.ensure_templates_exist()
        return {
            "answer_blank": str(self.answer_template_path),
            "a3_cover": str(self.a3_cover_template_path),
            "badge": str(self.badge_template_path),
        }

    def generate_answer_blank(
        self,
        qr_payload: str,
        tour_number: int,
        task_number: int,
        mode: str,
        tour_task: str | None = None,
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
                "{{TOUR_TASK}}": tour_task or f"{tour_number}/{task_number}",
            },
        )
        qr_bytes = self._build_qr_png(qr_payload)
        # QR in answer blank must not exceed 3 cm (30 mm) in width/height.
        self._replace_image_token(doc, "{{QR_IMAGE}}", qr_bytes, width_mm=23)
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
        self._replace_image_token(doc, "{{QR_IMAGE}}", qr_bytes, width_mm=28)
        return self._save_doc_to_bytes(doc)

    def generate_badge_docx(
        self,
        qr_payload: str,
        first_name: str,
        last_name: str,
        middle_name: str,
        role: str,
        participant_school: str,
        institution_name: str,
        competition_name: str,
        photo_bytes: bytes | None = None,
        template_bytes: bytes | None = None,
    ) -> bytes:
        """Render badge DOCX from editable template.

        Args:
            template_bytes: Pre-loaded template bytes. When provided, skips
                disk I/O and ``ensure_templates_exist()``. Pass this when
                generating many badges in a loop to avoid repeated disk reads.
        """
        if template_bytes is not None:
            doc = Document(io.BytesIO(template_bytes))
        else:
            self.ensure_templates_exist()
            doc = Document(str(self.badge_template_path))
        participant_name = " ".join(
            part for part in [last_name, first_name, middle_name] if part
        ).strip()
        self._replace_text_tokens(
            doc,
            {
                "{{FIRST_NAME}}": first_name or "",
                "{{LAST_NAME}}": last_name or "",
                "{{MIDDLE_NAME}}": middle_name or "",
                "{{ROLE}}": role or "",
                "{{PARTICIPANT_NAME}}": participant_name or "",
                "{{PARTICIPANT_SCHOOL}}": participant_school or "",
                "{{INSTITUTION_NAME}}": institution_name or "",
                "{{COMPETITION_NAME}}": competition_name or "",
            },
        )
        qr_bytes = self._build_qr_png(qr_payload)
        self._replace_image_token(doc, "{{QR_IMAGE}}", qr_bytes, width_mm=20, height_mm=20)
        optimized_photo_bytes = self._prepare_badge_photo(
            photo_bytes=photo_bytes,
            width_mm=30,
            height_mm=40,
        )
        self._replace_image_token(doc, "{{PHOTO}}", optimized_photo_bytes, width_mm=30, height_mm=40)
        return self._save_doc_to_bytes(doc)

    def import_badge_photos_zip(self, zip_bytes: bytes) -> int:
        """Replace badge photos directory from a ZIP archive."""
        self.ensure_templates_exist()
        if self.badge_photos_dir.exists():
            shutil.rmtree(self.badge_photos_dir)
        self.badge_photos_dir.mkdir(parents=True, exist_ok=True)

        imported = 0
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                ext = Path(info.filename).suffix.lower()
                if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
                    continue
                relative = Path(info.filename)
                target = (self.badge_photos_dir / relative).resolve()
                if self.badge_photos_dir.resolve() not in target.parents and target != self.badge_photos_dir.resolve():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(info))
                imported += 1

        self._badge_photo_index = None
        return imported

    def find_badge_photo(
        self,
        city: str | None,
        institution_name: str | None,
        last_name: str,
        first_name: str,
        middle_name: str,
    ) -> bytes | None:
        """Find participant photo by city/institution/FIO path convention."""
        self.ensure_templates_exist()
        index = self._get_badge_photo_index()
        fio = "_".join(part for part in [last_name, first_name, middle_name] if part).strip("_")
        if not fio:
            return None

        keys = [
            self._normalize_photo_key(f"{city or ''}/{institution_name or ''}/{fio}"),
            self._normalize_photo_key(f"{institution_name or ''}/{fio}"),
            self._normalize_photo_key(fio),
        ]

        for key in keys:
            path = index.get(key)
            if path and path.exists():
                try:
                    return path.read_bytes()
                except Exception:  # noqa: BLE001
                    continue
        return None

    @staticmethod
    def is_docx_to_pdf_available() -> bool:
        return shutil.which("soffice") is not None

    def install_fonts_system_wide(self) -> int:
        """Copy fonts from fonts_dir to /usr/local/share/fonts/olimpqr/ and rebuild fc-cache.

        Called explicitly after font upload and lazily once per process at conversion time.
        Returns the number of font files installed.
        """
        import os

        if not self.fonts_dir.exists():
            return 0

        font_files = [
            f for f in self.fonts_dir.iterdir()
            if f.is_file() and f.suffix.lower() in {".ttf", ".otf"}
        ]
        if not font_files:
            return 0

        system_dir = Path("/usr/local/share/fonts/olimpqr")
        try:
            system_dir.mkdir(parents=True, exist_ok=True)
            for font_file in font_files:
                shutil.copy2(font_file, system_dir / font_file.name)
            subprocess.run(
                ["fc-cache", "-f", str(system_dir)],
                capture_output=True,
                timeout=30,
            )
            WordTemplateGenerator._system_fonts_pid = os.getpid()
        except Exception:  # noqa: BLE001
            # Non-fatal: fonts may already be available via another mechanism.
            WordTemplateGenerator._system_fonts_pid = os.getpid()

        return len(font_files)

    def _ensure_system_fonts(self) -> None:
        """Install custom fonts system-wide once per process lifetime (lazy)."""
        import os

        if WordTemplateGenerator._system_fonts_pid == os.getpid():
            return
        self.install_fonts_system_wide()

    def convert_docx_files_to_pdf(self, files: dict[str, bytes]) -> dict[str, bytes]:
        """Convert DOCX files to PDF using parallel LibreOffice workers.

        Files are split into batches; up to DOCX_TO_PDF_MAX_WORKERS batches
        run simultaneously, each in its own isolated tmp directory and
        LibreOffice user-profile so instances do not conflict.
        """
        if not files:
            return {}
        soffice = shutil.which("soffice")
        if not soffice:
            raise RuntimeError("LibreOffice (soffice) is not installed")

        # Ensure custom fonts are installed system-wide once per process.
        self._ensure_system_fonts()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Build safe-named file list.
            used_safe_names: set[str] = set()
            mapped_files: list[tuple[str, str, bytes]] = []
            for name, content in files.items():
                safe_name = self._build_unique_safe_docx_name(name=name, used=used_safe_names)
                mapped_files.append((name, safe_name, content))

            # Split into batches.
            batch_size = max(1, self.DOCX_TO_PDF_BATCH_SIZE)
            batches = [
                mapped_files[i : i + batch_size]
                for i in range(0, len(mapped_files), batch_size)
            ]

            result: dict[str, bytes] = {}

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.DOCX_TO_PDF_MAX_WORKERS
            ) as executor:
                future_to_batch = {
                    executor.submit(
                        self._run_soffice_batch,
                        soffice,
                        batch,
                        tmp_path / f"worker_{wid}",
                    ): batch
                    for wid, batch in enumerate(batches)
                }
                for future in concurrent.futures.as_completed(future_to_batch):
                    result.update(future.result())  # propagates exceptions

            return result

    def _run_soffice_batch(
        self,
        soffice: str,
        batch: list[tuple[str, str, bytes]],
        worker_dir: Path,
    ) -> dict[str, bytes]:
        """Convert one batch of DOCX files to PDF in an isolated worker directory."""
        worker_dir.mkdir(parents=True, exist_ok=True)
        lo_profile = worker_dir / "lo_profile"
        lo_profile.mkdir(parents=True, exist_ok=True)

        docx_paths: list[str] = []
        for _, safe_name, content in batch:
            file_path = worker_dir / safe_name
            file_path.write_bytes(content)
            docx_paths.append(str(file_path))

        batch_timeout = max(
            self.DOCX_TO_PDF_TIMEOUT_SEC,
            len(batch) * self.DOCX_TO_PDF_SEC_PER_FILE,
        )

        command = [
            soffice,
            "--headless",
            "--norestore",
            "--nolockcheck",
            "--nodefault",
            "--nofirststartwizard",
            f"-env:UserInstallation=file://{lo_profile.as_posix()}",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            str(worker_dir),
            *docx_paths,
        ]
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=batch_timeout,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            raise RuntimeError(
                f"DOCX->PDF conversion failed: {stderr or stdout or 'unknown error'}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"DOCX->PDF conversion timeout ({batch_timeout}s) on batch starting with {batch[0][1]}"
            ) from exc

        result: dict[str, bytes] = {}
        for original_name, safe_name, _ in batch:
            pdf_path = (worker_dir / safe_name).with_suffix(".pdf")
            if not pdf_path.exists():
                raise RuntimeError(f"Converted PDF not found for {original_name}")
            result[original_name] = pdf_path.read_bytes()
        return result

    @staticmethod
    def _build_unique_safe_docx_name(name: str, used: set[str]) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
        if not safe.lower().endswith(".docx"):
            safe = f"{safe}.docx"
        stem = Path(safe).stem
        suffix = Path(safe).suffix
        candidate = safe
        counter = 1
        while candidate in used:
            candidate = f"{stem}_{counter}{suffix}"
            counter += 1
        used.add(candidate)
        return candidate

    def _prepare_badge_photo(
        self,
        photo_bytes: bytes | None,
        width_mm: float,
        height_mm: float,
    ) -> bytes | None:
        """Resize/compress participant photo close to print size for faster DOCX/PDF generation."""
        if not photo_bytes:
            return None
        try:
            target_w = max(int((width_mm / 25.4) * self.BADGE_PHOTO_DPI), 1)
            target_h = max(int((height_mm / 25.4) * self.BADGE_PHOTO_DPI), 1)
            with Image.open(io.BytesIO(photo_bytes)) as img:
                img = ImageOps.exif_transpose(img).convert("RGB")
                contained = ImageOps.contain(img, (target_w, target_h), Image.Resampling.LANCZOS)
                canvas = Image.new("RGB", (target_w, target_h), (255, 255, 255))
                offset_x = (target_w - contained.width) // 2
                offset_y = (target_h - contained.height) // 2
                canvas.paste(contained, (offset_x, offset_y))

                out = io.BytesIO()
                canvas.save(out, format="JPEG", quality=82, optimize=True)
                return out.getvalue()
        except Exception:  # noqa: BLE001
            return photo_bytes

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

    def _replace_image_token(
        self,
        doc: Document,
        token: str,
        image_bytes: bytes | None,
        width_mm: float,
        height_mm: float | None = None,
    ) -> None:
        if image_bytes is None:
            self._replace_text_tokens(doc, {token: ""})
            return

        for paragraph in self._iter_all_paragraphs(doc):
            if token in paragraph.text:
                self._insert_image_in_paragraph(
                    paragraph,
                    token=token,
                    image_bytes=image_bytes,
                    width_mm=width_mm,
                    height_mm=height_mm,
                )
                return

        # Fallback: append image at the end if token not found.
        paragraph = doc.add_paragraph()
        run = paragraph.add_run()
        if height_mm is not None:
            run.add_picture(io.BytesIO(image_bytes), width=Mm(width_mm), height=Mm(height_mm))
        else:
            run.add_picture(io.BytesIO(image_bytes), width=Mm(width_mm))

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

        # Also search tokens inside floating text boxes (w:txbxContent).
        # Badge templates commonly use text boxes for precise element placement.
        yield from self._iter_text_box_paragraphs(doc)

    @staticmethod
    def _iter_text_box_paragraphs(doc: Document) -> Iterable:
        """Yield Paragraph objects inside w:txbxContent elements (floating text boxes).

        python-docx does not expose text box content via its public API, so we
        iterate the raw XML tree.  The resulting Paragraph objects are fully
        functional for both text replacement and image insertion because the
        underlying elements remain attached to the document XML tree and can
        therefore resolve part relationships (needed by run.add_picture()).
        """
        from docx.oxml.ns import qn
        from docx.text.paragraph import Paragraph
        from docx.table import Table

        body = doc.element.body
        for txbx in body.iter(qn("w:txbxContent")):
            for p_elem in txbx.findall(qn("w:p")):
                yield Paragraph(p_elem, body)
            for tbl_elem in txbx.findall(qn("w:tbl")):
                yield from WordTemplateGenerator._iter_table_paragraphs(
                    Table(tbl_elem, body)
                )

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
    def _insert_image_in_paragraph(
        paragraph,
        token: str,
        image_bytes: bytes,
        width_mm: float,
        height_mm: float | None = None,
    ) -> None:
        text = paragraph.text
        before, after = text.split(token, 1)

        if paragraph.runs:
            paragraph.runs[0].text = before
            for run in paragraph.runs[1:]:
                run.text = ""
        else:
            paragraph.add_run(before)

        image_run = paragraph.add_run()
        if height_mm is not None:
            image_run.add_picture(
                io.BytesIO(image_bytes),
                width=Mm(width_mm),
                height=Mm(height_mm),
            )
        else:
            image_run.add_picture(io.BytesIO(image_bytes), width=Mm(width_mm))
        if after:
            paragraph.add_run(after)

    def _get_badge_photo_index(self) -> dict[str, Path]:
        if self._badge_photo_index is not None:
            return self._badge_photo_index

        index: dict[str, Path] = {}
        if self.badge_photos_dir.exists():
            for path in self.badge_photos_dir.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                    continue
                rel = path.relative_to(self.badge_photos_dir)
                normalized_rel = self._normalize_photo_key(str(rel.with_suffix("")).replace("\\", "/"))
                normalized_stem = self._normalize_photo_key(path.stem)
                index[normalized_rel] = path
                index.setdefault(normalized_stem, path)

        self._badge_photo_index = index
        return index

    @staticmethod
    def _normalize_photo_key(value: str) -> str:
        cleaned = re.sub(r"[^\w/]+", "_", value, flags=re.UNICODE).strip("_")
        cleaned = cleaned.replace("\\", "/")
        cleaned = re.sub(r"/+", "/", cleaned)
        return cleaned.lower()

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

    @staticmethod
    def _create_default_badge_template(path: Path) -> None:
        doc = Document()
        section = doc.sections[0]
        section.page_width = Mm(90)
        section.page_height = Mm(120)
        section.left_margin = Mm(5)
        section.right_margin = Mm(5)
        section.top_margin = Mm(5)
        section.bottom_margin = Mm(5)

        title = doc.add_paragraph("ШАБЛОН БЕЙДЖА")
        title.alignment = 1
        title.runs[0].bold = True
        title.runs[0].font.size = Pt(13)

        comp = doc.add_paragraph("{{COMPETITION_NAME}}")
        comp.alignment = 1
        comp.runs[0].font.size = Pt(10)

        role = doc.add_paragraph("{{ROLE}}")
        role.alignment = 1
        role.runs[0].bold = True
        role.runs[0].font.size = Pt(10)

        name = doc.add_paragraph("{{LAST_NAME}} {{FIRST_NAME}} {{MIDDLE_NAME}}")
        name.alignment = 1
        name.runs[0].bold = True
        name.runs[0].font.size = Pt(14)

        school = doc.add_paragraph("{{PARTICIPANT_SCHOOL}}")
        school.alignment = 1
        school.runs[0].font.size = Pt(10)

        institution = doc.add_paragraph("{{INSTITUTION_NAME}}")
        institution.alignment = 1
        institution.runs[0].font.size = Pt(10)

        photo = doc.add_paragraph("{{PHOTO}}")
        photo.alignment = 1

        qr = doc.add_paragraph("{{QR_IMAGE}}")
        qr.alignment = 1

        hint = doc.add_paragraph(
            "Токены: {{QR_IMAGE}}, {{PHOTO}}, {{COMPETITION_NAME}}, {{ROLE}}, "
            "{{LAST_NAME}}, {{FIRST_NAME}}, {{MIDDLE_NAME}}, "
            "{{PARTICIPANT_NAME}}, {{PARTICIPANT_SCHOOL}}, {{INSTITUTION_NAME}}."
        )
        hint.alignment = 1
        for run in hint.runs:
            run.font.size = Pt(8)

        doc.save(str(path))
