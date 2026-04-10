"""Celery task for asynchronous badge PDF generation."""

from __future__ import annotations

import logging
import re
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker, joinedload

from .celery_app import celery_app
from ..storage import MinIOStorage
from ..database.models import (
    RegistrationModel,
    CompetitionModel,
    ParticipantModel,
    BadgePhotoModel,
    BadgeTemplateModel,
)
from ...config import settings

logger = logging.getLogger(__name__)

_sync_engine = None
_SessionLocal = None

BADGE_PDF_BUCKET = settings.minio_bucket_sheets
BADGE_PDF_PREFIX = "badge-pdfs"


def _get_sync_url(async_url: str) -> str:
    url = async_url
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg2")
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _get_sync_session() -> Session:
    global _sync_engine, _SessionLocal
    if _sync_engine is None:
        sync_url = _get_sync_url(settings.database_url)
        _sync_engine = create_engine(sync_url)
        _SessionLocal = sessionmaker(bind=_sync_engine)
    return _SessionLocal()


def _normalize_photo_key(value: str) -> str:
    cleaned = re.sub(r"[^\w/]+", "_", value, flags=re.UNICODE).strip("_")
    cleaned = cleaned.replace("\\", "/")
    cleaned = re.sub(r"/+", "/", cleaned)
    return cleaned.lower()


def _split_full_name(full_name: str) -> tuple[str, str, str]:
    parts = [p for p in re.split(r"\s+", (full_name or "").strip()) if p]
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", ""
    if len(parts) == 2:
        return parts[0], parts[1], ""
    return parts[0], parts[1], " ".join(parts[2:])


def _build_photo_index(session: Session) -> dict[str, bytes]:
    rows = session.query(BadgePhotoModel.normalized_key, BadgePhotoModel.image_bytes).all()
    index: dict[str, bytes] = {}
    for row in rows:
        key = (row.normalized_key or "").strip().lower()
        if not key:
            continue
        index[key] = row.image_bytes
        parts = [p for p in key.split("/") if p]
        for n in range(1, min(4, len(parts))):
            alias = "/".join(parts[-n:])
            index.setdefault(alias, row.image_bytes)
    return index


def _find_photo(index: dict[str, bytes], city: str | None, institution: str | None,
                last: str, first: str, middle: str) -> bytes | None:
    fio = "_".join(p for p in [last, first, middle] if p).strip("_")
    if not fio:
        return None
    keys = [
        _normalize_photo_key(f"{city or ''}/{institution or ''}/{fio}"),
        _normalize_photo_key(f"{institution or ''}/{fio}"),
        _normalize_photo_key(fio),
    ]
    for k in keys:
        v = index.get(k)
        if v:
            return v
    return None


@celery_app.task(
    name="olimpqr.generate_badges_pdf",
    bind=True,
    max_retries=0,
    time_limit=2700,      # hard kill after 45 min
    soft_time_limit=2400, # soft limit at 40 min — allows cleanup
)
def generate_badges_pdf(self, competition_id: str) -> dict:
    """Generate badge PDF for all registered participants.

    Stores the resulting PDF in MinIO and returns the object name.
    Progress is reported via Celery's update_state so the API can poll it.
    """
    from ..pdf.badge_template_pdf_generator import BadgeTemplatePdfGenerator, TemplateBadgePdfItem
    from ..pdf.json_badge_generator import JsonBadgeGenerator

    comp_uuid = UUID(competition_id)
    session = _get_sync_session()
    try:
        # ── 1. Load competition ──────────────────────────────────────────────
        competition = session.get(CompetitionModel, comp_uuid)
        if not competition:
            return {"status": "failed", "message": "Олимпиада не найдена"}

        # ── 1b. Load badge template (JSON-based, if exists) ──────────────────
        badge_template = (
            session.query(BadgeTemplateModel)
            .where(BadgeTemplateModel.competition_id == comp_uuid)
            .first()
        )

        # ── 2. Load registrations + related data ─────────────────────────────
        registrations = (
            session.query(RegistrationModel)
            .where(RegistrationModel.competition_id == comp_uuid)
            .options(
                joinedload(RegistrationModel.entry_token),
                joinedload(RegistrationModel.participant).joinedload(ParticipantModel.institution),
            )
            .order_by(RegistrationModel.created_at)
            .all()
        )

        # ── 3. Load badge photos ──────────────────────────────────────────────
        self.update_state(state="PROGRESS", meta={"stage": "loading", "current": 0, "total": 0})
        photo_index = _build_photo_index(session)

        prepared: list[dict] = []
        total = len(registrations)

        if badge_template is not None:
            # ── 4a. Generate badge PDFs via JSON template (ReportLab) ─────────
            json_gen = JsonBadgeGenerator()
            template_config = badge_template.config_json or {}
            background_bytes = badge_template.background_image_bytes

            for idx, reg in enumerate(registrations, start=1):
                self.update_state(
                    state="PROGRESS",
                    meta={"stage": "generating", "current": idx, "total": total},
                )
                participant = reg.participant
                if not participant:
                    continue
                if not (reg.entry_token and reg.entry_token.raw_token):
                    continue

                institution_name = ""
                if participant.institution:
                    institution_name = participant.institution.name or ""

                last, first, middle = _split_full_name(participant.full_name)
                photo_bytes = _find_photo(
                    photo_index,
                    city=participant.institution_location,
                    institution=institution_name,
                    last=last, first=first, middle=middle,
                )

                participant_data = {
                    "LAST_NAME": last,
                    "FIRST_NAME": first,
                    "MIDDLE_NAME": middle,
                    "ROLE": "УЧАСТНИК",
                    "QR_PAYLOAD": reg.entry_token.raw_token,
                    "PHOTO_BYTES": photo_bytes,
                    "COMPETITION_NAME": competition.name,
                    "INSTITUTION_NAME": institution_name,
                }
                pdf_bytes_single = json_gen.generate_badge_pdf(
                    template_config, participant_data, background_bytes
                )
                prepared.append({
                    "institution": institution_name,
                    "full_name": participant.full_name or "",
                    "pdf": pdf_bytes_single,
                })

            prepared.sort(key=lambda x: (x["institution"], x["full_name"]))
            if not prepared:
                return {"status": "failed", "message": "Нет участников с токенами"}

            # ── 5a. Group into A4 pages (skip DOCX→PDF conversion step) ──────
            self.update_state(
                state="PROGRESS",
                meta={"stage": "assembling", "current": len(prepared), "total": len(prepared)},
            )
            items = [
                TemplateBadgePdfItem(institution=p["institution"], pdf_bytes=p["pdf"])
                for p in prepared
            ]
            per_page = badge_template.print_per_page or 4
            width_mm = float(template_config.get("width_mm", 90))
            height_mm = float(template_config.get("height_mm", 120))
            pdf_bytes = BadgeTemplatePdfGenerator().generate_grouped_pdf(
                competition.name, items,
                per_page=per_page,
                badge_w_mm=width_mm,
                badge_h_mm=height_mm,
            )

        else:
            # ── 4b. Fallback: DOCX template + LibreOffice ─────────────────────
            from ..docx.template_generator import WordTemplateGenerator

            word_generator = WordTemplateGenerator()
            word_generator.ensure_templates_exist()

            template_bytes: bytes | None = None
            if word_generator.badge_template_path.exists():
                template_bytes = word_generator.badge_template_path.read_bytes()

            for idx, reg in enumerate(registrations, start=1):
                self.update_state(
                    state="PROGRESS",
                    meta={"stage": "generating", "current": idx, "total": total},
                )
                participant = reg.participant
                if not participant:
                    continue
                if not (reg.entry_token and reg.entry_token.raw_token):
                    continue

                institution_name = ""
                if participant.institution:
                    institution_name = participant.institution.name or ""

                last, first, middle = _split_full_name(participant.full_name)
                photo_bytes = _find_photo(
                    photo_index,
                    city=participant.institution_location,
                    institution=institution_name,
                    last=last, first=first, middle=middle,
                )

                docx_bytes = word_generator.generate_badge_docx(
                    qr_payload=reg.entry_token.raw_token,
                    first_name=first,
                    last_name=last,
                    middle_name=middle,
                    role="УЧАСТНИК",
                    participant_school=participant.school or "",
                    institution_name=institution_name,
                    competition_name=competition.name,
                    photo_bytes=photo_bytes,
                    template_bytes=template_bytes,
                )
                prepared.append({
                    "institution": institution_name,
                    "full_name": participant.full_name or "",
                    "docx": docx_bytes,
                })

            prepared.sort(key=lambda x: (x["institution"], x["full_name"]))
            if not prepared:
                return {"status": "failed", "message": "Нет участников с токенами"}

            self.update_state(
                state="PROGRESS",
                meta={"stage": "converting", "current": 0, "total": len(prepared)},
            )
            docx_files: dict[str, bytes] = {}
            name_to_institution: dict[str, str] = {}
            for i, item in enumerate(prepared, start=1):
                fname = f"badge_{i:04d}.docx"
                docx_files[fname] = item["docx"]
                name_to_institution[fname] = item["institution"]

            converted = word_generator.convert_docx_files_to_pdf(docx_files)

            self.update_state(
                state="PROGRESS",
                meta={"stage": "assembling", "current": len(prepared), "total": len(prepared)},
            )
            items = [
                TemplateBadgePdfItem(
                    institution=name_to_institution[fname],
                    pdf_bytes=converted[fname],
                )
                for fname in docx_files
            ]
            pdf_bytes = BadgeTemplatePdfGenerator().generate_grouped_pdf(competition.name, items)

        # ── 7. Upload to MinIO ────────────────────────────────────────────────
        object_name = f"{BADGE_PDF_PREFIX}/badges_{competition_id}.pdf"
        storage = MinIOStorage()
        # Ensure bucket exists (MinIOStorage only creates predefined buckets)
        try:
            if not storage.client.bucket_exists(BADGE_PDF_BUCKET):
                storage.client.make_bucket(BADGE_PDF_BUCKET)
        except Exception:
            pass
        storage.upload_file(
            bucket=BADGE_PDF_BUCKET,
            object_name=object_name,
            data=pdf_bytes,
            content_type="application/pdf",
        )

        logger.info("Badge PDF generated: %s (%d badges)", object_name, len(prepared))
        return {
            "status": "completed",
            "object_name": object_name,
            "count": len(prepared),
        }

    except Exception as exc:
        logger.error("Badge PDF generation failed for %s: %s", competition_id, exc, exc_info=True)
        return {"status": "failed", "message": str(exc)}
    finally:
        session.close()
