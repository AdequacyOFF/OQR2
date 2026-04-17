"""Celery tasks for asynchronous badge PDF and blanks ZIP generation."""

from __future__ import annotations

import io
import logging
import re
import zipfile
from typing import Any
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
    StaffBadgeModel,
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


# ── helpers for blanks ZIP generation ────────────────────────────────────────

BLANKS_ZIP_BUCKET = settings.minio_bucket_sheets
BLANKS_ZIP_PREFIX = "blanks-zips"


def _slugify(value: str) -> str:
    safe = re.sub(r"[^\w\-. ]+", "_", value, flags=re.UNICODE).strip()
    safe = re.sub(r"\s+", "_", safe)
    return safe[:80] or "participant"


def _derive_team_name_sync(participant: ParticipantModel) -> str:
    inst = participant.institution
    location = (participant.institution_location or "").strip()
    if inst:
        return f"{inst.name} ({location})" if location else inst.name
    return (participant.school or "").strip() or "Команда"


def _extract_tours(competition: CompetitionModel) -> list[dict[str, Any]]:
    allowed_modes = {"individual", "individual_captains", "team"}
    raw_tours = (competition.special_settings or {}).get("tours")
    normalized: list[dict[str, Any]] = []
    if not isinstance(raw_tours, list):
        return normalized
    for idx, item in enumerate(raw_tours, start=1):
        if not isinstance(item, dict):
            continue
        tour_number = int(item.get("tour_number") or idx)
        mode = str(item.get("mode") or "individual").strip()
        if mode not in allowed_modes:
            mode = "individual"
        task_numbers: list[int] = []
        for t in (item.get("task_numbers") or item.get("tasks") or [1]):
            try:
                val = int(t)
                if val > 0:
                    task_numbers.append(val)
            except Exception:  # noqa: BLE001
                continue
        if not task_numbers:
            task_numbers = [1]
        captains_task = bool(item.get("captains_task", False))
        captains_task_numbers: list[int] = []
        for ct in (item.get("captains_task_numbers") or []):
            try:
                val = int(ct)
                if val > 0:
                    captains_task_numbers.append(val)
            except Exception:  # noqa: BLE001
                continue
        normalized.append({
            "tour_number": tour_number,
            "mode": mode,
            "task_numbers": task_numbers,
            "captains_task": captains_task,
            "captains_task_numbers": captains_task_numbers,
        })
    return normalized


@celery_app.task(
    name="olimpqr.generate_blanks_zip",
    bind=True,
    max_retries=0,
    time_limit=3600,
    soft_time_limit=3300,
)
def generate_blanks_zip(self, competition_id: str) -> dict:
    """Generate answer-blanks ZIP for all admitted participants.

    Stores the resulting ZIP in MinIO and returns the object name.
    Progress is reported via Celery's update_state so the API can poll it.
    """
    from ..docx.template_generator import WordTemplateGenerator

    comp_uuid = UUID(competition_id)
    session = _get_sync_session()
    try:
        # ── 1. Load competition ──────────────────────────────────────────────
        competition = session.get(CompetitionModel, comp_uuid)
        if not competition:
            return {"status": "failed", "message": "Олимпиада не найдена"}

        tours = _extract_tours(competition)
        has_team_tours = any(str(t["mode"]) == "team" for t in tours)
        mode_labels = {
            "individual": "Индивидуальный",
            "individual_captains": "Индивидуальный (капитаны)",
            "team": "Командный",
        }

        # ── 2. Load registrations ────────────────────────────────────────────
        self.update_state(state="PROGRESS", meta={"stage": "loading", "current": 0, "total": 0, "participant": ""})
        registrations = (
            session.query(RegistrationModel)
            .where(RegistrationModel.competition_id == comp_uuid)
            .options(
                joinedload(RegistrationModel.participant).joinedload(ParticipantModel.institution),
                joinedload(RegistrationModel.entry_token),
                joinedload(RegistrationModel.attempts),
            )
            .order_by(RegistrationModel.created_at)
            .all()
        )

        total = len(registrations)
        word_generator = WordTemplateGenerator()
        template_paths = word_generator.get_template_paths()
        storage = MinIOStorage()
        zip_buffer = io.BytesIO()
        added_files = 0
        errors: list[str] = []

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # Include editable templates
            for kind, arcname in [
                ("answer_blank", "_templates/special_answer_blank_template.docx"),
                ("a3_cover", "_templates/special_cover_a3_template.docx"),
            ]:
                try:
                    zf.write(template_paths[kind], arcname=arcname)
                    added_files += 1
                except Exception:  # noqa: BLE001
                    pass

            # ── 3. Per-participant individual/captains blanks ─────────────────
            for idx, reg in enumerate(registrations, start=1):
                participant = reg.participant
                if not participant or not reg.attempts:
                    continue

                participant_name = participant.full_name or str(participant.id)
                self.update_state(
                    state="PROGRESS",
                    meta={"stage": "generating", "current": idx, "total": total, "participant": participant_name},
                )

                attempt = reg.attempts[0]
                folder = _slugify(f"{participant_name}_{participant.id}")
                individual_root = f"Личный зачет/{folder}" if has_team_tours else folder

                for tour in tours:
                    tour_number = int(tour["tour_number"])
                    mode = str(tour["mode"])
                    mode_label = mode_labels.get(mode, mode)
                    task_numbers = tour["task_numbers"]

                    if mode == "team":
                        continue

                    cover_qr = f"attempt:{attempt.id}:tour:{tour_number}:cover"
                    try:
                        cover_docx = word_generator.generate_a3_cover(
                            qr_payload=cover_qr, tour_number=tour_number, mode=mode_label
                        )
                        zf.writestr(f"{individual_root}/tour_{tour_number}/A3_tour_{tour_number}.docx", cover_docx)
                        added_files += 1
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{participant_name} A3 тур {tour_number}: {exc}")

                    for task_number in task_numbers:
                        task_qr = f"attempt:{attempt.id}:tour:{tour_number}:task:{task_number}"
                        try:
                            task_docx = word_generator.generate_answer_blank(
                                qr_payload=task_qr, tour_number=tour_number,
                                task_number=int(task_number), mode=mode_label,
                            )
                            task_folder = f"{individual_root}/tour_{tour_number}/task_{task_number}"
                            zf.writestr(f"{task_folder}/task_{task_number}.docx", task_docx)
                            added_files += 1
                            for extra_i in range(1, 6):
                                extra_docx = word_generator.generate_answer_blank(
                                    qr_payload=task_qr, tour_number=tour_number,
                                    task_number=int(task_number), mode=mode_label,
                                    tour_task=f"{tour_number}/{task_number}/{extra_i}",
                                )
                                zf.writestr(
                                    f"{task_folder}/дополнительные бланки/extra_{extra_i}.docx",
                                    extra_docx,
                                )
                                added_files += 1
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"{participant_name} тур {tour_number} задание {task_number}: {exc}")

                    if tour.get("captains_task") and getattr(participant, "is_captain", False):
                        cap_task_numbers = tour.get("captains_task_numbers") or [1]
                        cap_folder = f"{individual_root}/tour_{tour_number}/Задания для капитанов"
                        for cap_task_num in cap_task_numbers:
                            cap_qr = f"attempt:{attempt.id}:tour:{tour_number}:captains_task:{cap_task_num}"
                            try:
                                cap_docx = word_generator.generate_answer_blank(
                                    qr_payload=cap_qr, tour_number=tour_number,
                                    task_number=int(cap_task_num), mode="Задание для капитанов",
                                )
                                zf.writestr(f"{cap_folder}/задание_{cap_task_num}.docx", cap_docx)
                                added_files += 1
                                for extra_i in range(1, 6):
                                    cap_extra = word_generator.generate_answer_blank(
                                        qr_payload=cap_qr, tour_number=tour_number,
                                        task_number=int(cap_task_num), mode="Задание для капитанов",
                                        tour_task=f"{tour_number}/cap/{cap_task_num}/{extra_i}",
                                    )
                                    zf.writestr(
                                        f"{cap_folder}/дополнительные бланки/extra_{cap_task_num}_{extra_i}.docx",
                                        cap_extra,
                                    )
                                    added_files += 1
                            except Exception as exc:  # noqa: BLE001
                                errors.append(f"{participant_name} капитаны тур {tour_number}: {exc}")

            # ── 4. Team tour blanks (one set per institution, captain's attempt) ─
            if has_team_tours:
                team_tour_list = [t for t in tours if str(t["mode"]) == "team"]
                captain_attempts: dict[str, tuple] = {}
                for reg in registrations:
                    p = reg.participant
                    if not p or not reg.attempts:
                        continue
                    if not getattr(p, "is_captain", False):
                        continue
                    inst_name = _derive_team_name_sync(p)
                    inst_slug = _slugify(inst_name)
                    if inst_slug not in captain_attempts:
                        captain_attempts[inst_slug] = (reg.attempts[0].id, inst_name)

                team_total = len(captain_attempts) * len(team_tour_list)
                team_idx = 0
                for inst_slug, (cap_attempt_id, inst_label) in captain_attempts.items():
                    team_folder = f"Командный зачет/{inst_slug}"
                    for tour in team_tour_list:
                        team_idx += 1
                        self.update_state(
                            state="PROGRESS",
                            meta={"stage": "team", "current": team_idx, "total": team_total, "participant": inst_label},
                        )
                        tour_number = int(tour["tour_number"])
                        mode_label = mode_labels.get(str(tour["mode"]), str(tour["mode"]))
                        task_numbers = tour["task_numbers"]

                        cover_qr = f"attempt:{cap_attempt_id}:tour:{tour_number}:cover"
                        try:
                            cover_docx = word_generator.generate_a3_cover(
                                qr_payload=cover_qr, tour_number=tour_number, mode=mode_label
                            )
                            zf.writestr(f"{team_folder}/tour_{tour_number}/A3_tour_{tour_number}.docx", cover_docx)
                            added_files += 1
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"Команда {inst_label} A3 тур {tour_number}: {exc}")

                        for task_number in task_numbers:
                            task_qr = f"attempt:{cap_attempt_id}:tour:{tour_number}:task:{task_number}"
                            try:
                                task_docx = word_generator.generate_answer_blank(
                                    qr_payload=task_qr, tour_number=tour_number,
                                    task_number=int(task_number), mode=mode_label,
                                )
                                task_folder_path = f"{team_folder}/tour_{tour_number}/task_{task_number}"
                                zf.writestr(f"{task_folder_path}/task_{task_number}.docx", task_docx)
                                added_files += 1
                                for extra_i in range(1, 6):
                                    extra_docx = word_generator.generate_answer_blank(
                                        qr_payload=task_qr, tour_number=tour_number,
                                        task_number=int(task_number), mode=mode_label,
                                        tour_task=f"{tour_number}/{task_number}/{extra_i}",
                                    )
                                    zf.writestr(
                                        f"{task_folder_path}/дополнительные бланки/extra_{extra_i}.docx",
                                        extra_docx,
                                    )
                                    added_files += 1
                            except Exception as exc:  # noqa: BLE001
                                errors.append(f"Команда {inst_label} тур {tour_number} задание {task_number}: {exc}")

        # ── 5. Upload to MinIO ────────────────────────────────────────────────
        self.update_state(
            state="PROGRESS",
            meta={"stage": "uploading", "current": total, "total": total, "participant": ""},
        )
        object_name = f"{BLANKS_ZIP_PREFIX}/blanks_{competition_id}.zip"
        try:
            if not storage.client.bucket_exists(BLANKS_ZIP_BUCKET):
                storage.client.make_bucket(BLANKS_ZIP_BUCKET)
        except Exception:  # noqa: BLE001
            pass
        zip_buffer.seek(0)
        storage.upload_file(
            bucket=BLANKS_ZIP_BUCKET,
            object_name=object_name,
            data=zip_buffer.read(),
            content_type="application/zip",
        )

        logger.info("Blanks ZIP generated: %s (%d files)", object_name, added_files)
        return {
            "status": "completed",
            "object_name": object_name,
            "added_files": added_files,
            "errors": errors,
        }

    except Exception as exc:
        logger.error("Blanks ZIP generation failed for %s: %s", competition_id, exc, exc_info=True)
        return {"status": "failed", "message": str(exc)}
    finally:
        session.close()


@celery_app.task(
    name="olimpqr.generate_staff_badges_pdf",
    bind=True,
    max_retries=0,
    time_limit=2700,
    soft_time_limit=2400,
)
def generate_staff_badges_pdf_task(
    self,
    competition_id: str | None,
    badge_ids: list[str] | None,
) -> dict:
    """Generate badge PDF for staff/leaders asynchronously.

    Stores the resulting PDF in MinIO and returns the object name.
    Progress is reported via Celery's update_state so the API can poll it.
    """
    from ..pdf.badge_template_pdf_generator import BadgeTemplatePdfGenerator, TemplateBadgePdfItem
    from ..pdf.json_badge_generator import JsonBadgeGenerator
    import uuid as _uuid

    session = _get_sync_session()
    try:
        self.update_state(state="PROGRESS", meta={"stage": "loading", "current": 0, "total": 0})

        # ── 1. Load staff badge records ──────────────────────────────────────
        query = session.query(StaffBadgeModel)
        if badge_ids:
            parsed_ids = [_uuid.UUID(bid) for bid in badge_ids]
            query = query.filter(StaffBadgeModel.id.in_(parsed_ids))
        elif competition_id:
            query = query.filter(StaffBadgeModel.competition_id == _uuid.UUID(competition_id))
        else:
            return {"status": "failed", "message": "Необходимо указать competition_id или badge_ids"}

        badges = query.order_by(StaffBadgeModel.full_name).all()
        if not badges:
            return {"status": "failed", "message": "Нет бейджей для генерации"}

        # ── 2. Load badge template ────────────────────────────────────────────
        comp_id = (
            _uuid.UUID(competition_id) if competition_id
            else badges[0].competition_id
        )
        template = None
        if comp_id:
            template = (
                session.query(BadgeTemplateModel)
                .where(BadgeTemplateModel.competition_id == comp_id)
                .first()
            )
        if not template:
            return {"status": "failed", "message": "Шаблон бейджа не найден для данной олимпиады"}

        config = template.config_json or {}
        background_bytes = template.background_image_bytes
        per_page = template.print_per_page or 4

        # ── 3. Generate per-badge PDFs ────────────────────────────────────────
        json_gen = JsonBadgeGenerator()
        badge_items: list[TemplateBadgePdfItem] = []
        total = len(badges)

        for idx, badge in enumerate(badges, start=1):
            self.update_state(
                state="PROGRESS",
                meta={"stage": "generating", "current": idx, "total": total},
            )
            name_parts = (badge.full_name or "").strip().split()
            last_name = name_parts[0] if name_parts else ""
            first_name = name_parts[1] if len(name_parts) > 1 else ""
            middle_name = " ".join(name_parts[2:]) if len(name_parts) > 2 else ""

            participant_data: dict[str, Any] = {
                "LAST_NAME": last_name,
                "FIRST_NAME": first_name,
                "MIDDLE_NAME": middle_name,
                "ROLE": badge.role or "",
                "INSTITUTION_NAME": badge.institution or "",
                "COMPETITION_NAME": "",
                "QR_PAYLOAD": "",
                "PHOTO_BYTES": badge.photo_bytes,
            }
            pdf_bytes_single = json_gen.generate_badge_pdf(config, participant_data, background_bytes)
            badge_items.append(TemplateBadgePdfItem(
                institution="Руководители",
                pdf_bytes=pdf_bytes_single,
            ))

        # ── 4. Assemble A4 pages ──────────────────────────────────────────────
        self.update_state(
            state="PROGRESS",
            meta={"stage": "assembling", "current": total, "total": total},
        )
        badge_w_mm = float(config.get("width_mm", 90))
        badge_h_mm = float(config.get("height_mm", 120))
        pdf_bytes = BadgeTemplatePdfGenerator().generate_grouped_pdf(
            competition_name="Бейджи руководителей",
            items=badge_items,
            per_page=per_page,
            badge_w_mm=badge_w_mm,
            badge_h_mm=badge_h_mm,
        )

        # ── 5. Upload to MinIO ────────────────────────────────────────────────
        suffix = competition_id or "custom"
        object_name = f"{BADGE_PDF_PREFIX}/staff_badges_{suffix}.pdf"
        storage = MinIOStorage()
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

        logger.info("Staff badge PDF generated: %s (%d badges)", object_name, total)
        return {
            "status": "completed",
            "object_name": object_name,
            "count": total,
        }

    except Exception as exc:
        logger.error("Staff badge PDF generation failed: %s", exc, exc_info=True)
        return {"status": "failed", "message": str(exc)}
    finally:
        session.close()
