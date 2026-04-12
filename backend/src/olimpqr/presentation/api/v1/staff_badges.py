"""Staff badge API endpoints (Admin role)."""

from __future__ import annotations

import io
import logging
import re
import uuid
import zipfile
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....infrastructure.database import get_db
from ....infrastructure.database.models.staff_badge import StaffBadgeModel
from ....infrastructure.database.models.badge_template import BadgeTemplateModel
from ....infrastructure.pdf.json_badge_generator import JsonBadgeGenerator
from ....infrastructure.pdf.badge_template_pdf_generator import (
    BadgeTemplatePdfGenerator,
    TemplateBadgePdfItem,
)
from ....domain.value_objects import UserRole
from ....domain.entities import User
from ...dependencies import require_role
from ...schemas.staff_badge_schemas import (
    StaffBadgeCreateRequest,
    StaffBadgeGenerateRequest,
    StaffBadgeItem,
    StaffBadgeListResponse,
)
from ...utils.staff_import import parse_rukovoditeli_xlsx

logger = logging.getLogger(__name__)

router = APIRouter()

# ── helpers ──────────────────────────────────────────────────────────────

_NORMALIZE_RE = re.compile(r"[\s_/\\]+")


def _normalize_photo_key(path: str) -> str:
    """Normalize a zip path to a comparable key (lowercase, no extension)."""
    from pathlib import PurePosixPath

    p = PurePosixPath(path)
    stem = p.stem
    parts = list(p.parent.parts) + [stem]
    return "/".join(
        _NORMALIZE_RE.sub("_", part).strip("_").lower() for part in parts if part
    )


def _match_photo_from_zip(
    full_name: str,
    institution: str | None,
    city: str | None,
    photo_index: dict[str, tuple[bytes, str]],
) -> tuple[bytes, str] | None:
    """Try to find a matching photo in the zip index.

    Zip structure: City/Institution/Surname_Name_Patronymic.jpg
    """
    name_parts = full_name.strip().split()
    if not name_parts:
        return None

    name_key = "_".join(name_parts).lower()

    # Try full path: city/institution/name
    if city and institution:
        full_key = f"{city}/{institution}/{name_key}".lower()
        normalized = _normalize_photo_key(full_key)
        if normalized in photo_index:
            return photo_index[normalized]

    # Try institution/name
    if institution:
        partial_key = f"{institution}/{name_key}".lower()
        normalized = _normalize_photo_key(partial_key)
        if normalized in photo_index:
            return photo_index[normalized]

    # Try just name match
    for key, value in photo_index.items():
        if key.endswith(name_key.replace(" ", "_")):
            return value

    return None


def _build_photo_index(zip_bytes: bytes) -> dict[str, tuple[bytes, str]]:
    """Build a normalized-key → (bytes, content_type) index from a zip file."""
    index: dict[str, tuple[bytes, str]] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            lower = info.filename.lower()
            if not any(lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
                continue
            data = zf.read(info.filename)
            ct = "image/jpeg" if lower.endswith((".jpg", ".jpeg")) else "image/png"
            key = _normalize_photo_key(info.filename)
            index[key] = (data, ct)
    return index


def _model_to_item(m: StaffBadgeModel) -> StaffBadgeItem:
    return StaffBadgeItem(
        id=m.id,
        competition_id=m.competition_id,
        full_name=m.full_name,
        role=m.role,
        institution=m.institution,
        has_photo=m.photo_bytes is not None and len(m.photo_bytes) > 0,
        created_at=m.created_at,
    )


# ── CRUD endpoints ──────────────────────────────────────────────────────

@router.get("", response_model=StaffBadgeListResponse)
async def list_staff_badges(
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    competition_id: str | None = None,
):
    query = select(StaffBadgeModel).order_by(StaffBadgeModel.institution, StaffBadgeModel.full_name)
    if competition_id:
        query = query.where(StaffBadgeModel.competition_id == uuid.UUID(competition_id))
    result = await db.execute(query)
    models = result.scalars().all()
    return StaffBadgeListResponse(
        items=[_model_to_item(m) for m in models],
        total=len(models),
    )


@router.post("", response_model=StaffBadgeItem, status_code=status.HTTP_201_CREATED)
async def create_staff_badge(
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    full_name: str = Form(...),
    role: str = Form(...),
    competition_id: str | None = Form(None),
    institution: str | None = Form(None),
    photo: UploadFile | None = File(None),
):
    photo_bytes = None
    photo_ct = None
    if photo and photo.size:
        photo_bytes = await photo.read()
        photo_ct = photo.content_type

    model = StaffBadgeModel(
        id=uuid.uuid4(),
        competition_id=uuid.UUID(competition_id) if competition_id else None,
        full_name=full_name.strip(),
        role=role.strip(),
        institution=institution.strip() if institution else None,
        photo_bytes=photo_bytes,
        photo_content_type=photo_ct,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return _model_to_item(model)


@router.delete("/{badge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_staff_badge(
    badge_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(StaffBadgeModel).where(StaffBadgeModel.id == badge_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Бейдж не найден")
    await db.delete(model)
    await db.commit()


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_staff_badges(
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    competition_id: str | None = None,
):
    stmt = delete(StaffBadgeModel)
    if competition_id:
        stmt = stmt.where(StaffBadgeModel.competition_id == uuid.UUID(competition_id))
    await db.execute(stmt)
    await db.commit()


# ── Import endpoints ────────────────────────────────────────────────────

@router.post("/import-json", response_model=StaffBadgeListResponse)
async def import_staff_badges_json(
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    data_file: UploadFile = File(...),
    photos_zip: UploadFile | None = File(None),
    competition_id: str | None = Form(None),
):
    """Import staff badges from JSON file + optional photos zip."""
    import json

    raw = await data_file.read()
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Некорректный JSON файл")

    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="JSON должен содержать массив объектов")

    photo_index: dict[str, tuple[bytes, str]] = {}
    if photos_zip and photos_zip.size:
        zip_bytes = await photos_zip.read()
        photo_index = _build_photo_index(zip_bytes)

    comp_id = uuid.UUID(competition_id) if competition_id else None
    created: list[StaffBadgeModel] = []

    for item in items:
        full_name = str(item.get("full_name", item.get("name", ""))).strip()
        role_val = str(item.get("role", "")).strip()
        inst = str(item.get("institution", "")).strip() or None
        if not full_name or not role_val:
            continue

        photo_data = _match_photo_from_zip(full_name, inst, None, photo_index)
        model = StaffBadgeModel(
            id=uuid.uuid4(),
            competition_id=comp_id,
            full_name=full_name,
            role=role_val,
            institution=inst,
            photo_bytes=photo_data[0] if photo_data else None,
            photo_content_type=photo_data[1] if photo_data else None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(model)
        created.append(model)

    await db.commit()
    return StaffBadgeListResponse(
        items=[_model_to_item(m) for m in created],
        total=len(created),
    )


@router.post("/import-xlsx", response_model=StaffBadgeListResponse)
async def import_staff_badges_xlsx(
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    data_file: UploadFile = File(...),
    photos_zip: UploadFile | None = File(None),
    competition_id: str | None = Form(None),
):
    """Import staff badges from Руководители.xlsx + optional photos zip."""
    file_bytes = await data_file.read()
    parsed = parse_rukovoditeli_xlsx(file_bytes)
    if parsed is None:
        raise HTTPException(status_code=400, detail="Файл не соответствует шаблону Руководители.xlsx")

    photo_index: dict[str, tuple[bytes, str]] = {}
    if photos_zip and photos_zip.size:
        zip_bytes = await photos_zip.read()
        photo_index = _build_photo_index(zip_bytes)

    comp_id = uuid.UUID(competition_id) if competition_id else None
    created: list[StaffBadgeModel] = []

    for item in parsed:
        full_name = item["full_name"]
        role_val = item["role"]
        inst = item.get("institution")
        city = item.get("city")

        photo_data = _match_photo_from_zip(full_name, inst, city, photo_index)
        model = StaffBadgeModel(
            id=uuid.uuid4(),
            competition_id=comp_id,
            full_name=full_name,
            role=role_val,
            institution=inst,
            photo_bytes=photo_data[0] if photo_data else None,
            photo_content_type=photo_data[1] if photo_data else None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(model)
        created.append(model)

    await db.commit()
    return StaffBadgeListResponse(
        items=[_model_to_item(m) for m in created],
        total=len(created),
    )


# ── Photo upload for individual badge ───────────────────────────────────

@router.post("/{badge_id}/photo", response_model=StaffBadgeItem)
async def upload_staff_badge_photo(
    badge_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    photo: UploadFile = File(...),
):
    result = await db.execute(select(StaffBadgeModel).where(StaffBadgeModel.id == badge_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Бейдж не найден")

    model.photo_bytes = await photo.read()
    model.photo_content_type = photo.content_type
    model.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(model)
    return _model_to_item(model)


@router.get("/{badge_id}/photo")
async def get_staff_badge_photo(
    badge_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(StaffBadgeModel).where(StaffBadgeModel.id == badge_id))
    model = result.scalar_one_or_none()
    if not model or not model.photo_bytes:
        raise HTTPException(status_code=404, detail="Фото не найдено")
    return Response(
        content=model.photo_bytes,
        media_type=model.photo_content_type or "image/jpeg",
    )


# ── Badge PDF generation ────────────────────────────────────────────────

@router.post("/generate-pdf")
async def generate_staff_badges_pdf(
    request_body: StaffBadgeGenerateRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Generate PDF with staff badges using competition's badge template."""
    # Load badges
    query = select(StaffBadgeModel)
    if request_body.badge_ids:
        query = query.where(StaffBadgeModel.id.in_(request_body.badge_ids))
    elif request_body.competition_id:
        query = query.where(StaffBadgeModel.competition_id == request_body.competition_id)
    query = query.order_by(StaffBadgeModel.institution, StaffBadgeModel.full_name)

    result = await db.execute(query)
    badges = result.scalars().all()
    if not badges:
        raise HTTPException(status_code=400, detail="Нет бейджей для генерации")

    # Load badge template
    comp_id = request_body.competition_id or (badges[0].competition_id if badges else None)
    template = None
    if comp_id:
        tmpl_result = await db.execute(
            select(BadgeTemplateModel).where(BadgeTemplateModel.competition_id == comp_id)
        )
        template = tmpl_result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=400, detail="Шаблон бейджа не найден для данной олимпиады")

    config = template.config_json or {}
    background_bytes = template.background_image_bytes
    per_page = template.print_per_page or 4

    generator = JsonBadgeGenerator()
    badge_items: list[TemplateBadgePdfItem] = []

    for badge in badges:
        name_parts = badge.full_name.strip().split()
        last_name = name_parts[0] if name_parts else ""
        first_name = name_parts[1] if len(name_parts) > 1 else ""
        middle_name = " ".join(name_parts[2:]) if len(name_parts) > 2 else ""

        participant_data: dict[str, Any] = {
            "LAST_NAME": last_name,
            "FIRST_NAME": first_name,
            "MIDDLE_NAME": middle_name,
            "ROLE": badge.role,
            "INSTITUTION_NAME": badge.institution or "",
            "COMPETITION_NAME": "",
            "QR_PAYLOAD": "",
            "PHOTO_BYTES": badge.photo_bytes,
        }

        pdf_bytes = generator.generate_badge_pdf(config, participant_data, background_bytes)
        badge_items.append(TemplateBadgePdfItem(
            institution=badge.institution or "Руководители",
            pdf_bytes=pdf_bytes,
        ))

    # Compose grouped A4 PDF
    composer = BadgeTemplatePdfGenerator()
    badge_w_mm = float(config.get("width_mm", 90))
    badge_h_mm = float(config.get("height_mm", 120))
    final_pdf = composer.generate_grouped_pdf(
        competition_name="Бейджи руководителей",
        items=badge_items,
        per_page=per_page,
        badge_w_mm=badge_w_mm,
        badge_h_mm=badge_h_mm,
    )

    return Response(
        content=final_pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=staff_badges.pdf"},
    )
