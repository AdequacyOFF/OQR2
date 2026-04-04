"""Admin API endpoints."""

import csv
import io
import json
import re
import secrets
import zipfile
from html import escape
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ....infrastructure.database import get_db
from ....infrastructure.repositories import (
    UserRepositoryImpl,
    AuditLogRepositoryImpl,
    CompetitionRepositoryImpl,
    ScanRepositoryImpl,
    RegistrationRepositoryImpl,
    ParticipantRepositoryImpl,
    EntryTokenRepositoryImpl,
    InstitutionRepositoryImpl,
    AttemptRepositoryImpl,
    AnswerSheetRepositoryImpl,
    RoomRepositoryImpl,
    SeatAssignmentRepositoryImpl,
)
from ....infrastructure.security import hash_password
from ....infrastructure.storage import MinIOStorage
from ....infrastructure.pdf import SheetGenerator
from ....infrastructure.docx import WordTemplateGenerator
from ....domain.entities import User
from ....domain.value_objects import UserRole
from ....domain.services import TokenService
from ....application.use_cases.admission import ApproveAdmissionUseCase
from ....application.use_cases.registration.register_for_competition import (
    RegisterForCompetitionUseCase,
)
from ....config import settings
from ...schemas.admin_schemas import (
    CreateStaffRequest,
    UpdateUserRequest,
    UserListResponse,
    AdminUserResponse,
    AuditLogEntry,
    AuditLogListResponse,
    StatisticsResponse,
    AdminRegisterRequest,
    AdminRegisterResponse,
    AdminRegistrationItem,
    AdminRegistrationListResponse,
)
from ...dependencies import require_role

router = APIRouter()


_IMPORT_HEADER_ALIASES = {
    "full_name": {
        "full_name",
        "fio",
        "С„РёРѕ",
        "name",
        "participant_name",
        "participant",
    },
    "email": {"email", "РїРѕС‡С‚Р°", "e-mail", "mail"},
    "institution": {
        "institution",
        "institution_name",
        "school",
        "university",
        "РІСѓР·",
        "СѓС‡СЂРµР¶РґРµРЅРёРµ",
        "СѓС‡РµР±РЅРѕРµ СѓС‡СЂРµР¶РґРµРЅРёРµ",
    },
    "institution_location": {
        "institution_location",
        "location",
        "city",
        "campus",
        "РјРµСЃС‚РѕРїРѕР»РѕР¶РµРЅРёРµ",
        "РіРѕСЂРѕРґ",
        "РјРµСЃС‚РѕРїРѕР»РѕР¶РµРЅРёРµ РІСѓР·Р°",
        "РіРѕСЂРѕРґ РІСѓР·Р°",
    },
    "is_captain": {"is_captain", "captain", "РєР°РїРёС‚Р°РЅ", "РєР°РїРёС‚Р°РЅ/РЅРµ РєР°РїРёС‚Р°РЅ"},
    "dob": {"dob", "birth_date", "date_of_birth", "РґР°С‚Р° СЂРѕР¶РґРµРЅРёСЏ", "СЂРѕР¶РґРµРЅРёРµ"},
}


def _normalize_header(name: str) -> str:
    key = name.strip().lower()
    for canonical, aliases in _IMPORT_HEADER_ALIASES.items():
        if key in aliases:
            return canonical
    return key


def _normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        normalized[_normalize_header(str(key))] = value
    return normalized


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    normalized = str(value).strip().lower()
    return normalized in {"1", "true", "yes", "y", "РґР°", "РєР°РїРёС‚Р°РЅ"}


def _parse_dob(value: Any):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"РќРµ СѓРґР°Р»РѕСЃСЊ СЂР°СЃРїРѕР·РЅР°С‚СЊ РґР°С‚Сѓ СЂРѕР¶РґРµРЅРёСЏ: {value}")


def _slugify_folder_name(value: str) -> str:
    safe = re.sub(r"[^\w\-. ]+", "_", value, flags=re.UNICODE).strip()
    safe = re.sub(r"\s+", "_", safe)
    return safe[:80] or "participant"


def _parse_import_file(file_name: str, file_bytes: bytes) -> list[dict[str, Any]]:
    lower_name = file_name.lower()

    if lower_name.endswith(".json"):
        payload = json.loads(file_bytes.decode("utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("participants", [])
        if not isinstance(payload, list):
            raise ValueError("JSON РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ РјР°СЃСЃРёРІРѕРј СѓС‡Р°СЃС‚РЅРёРєРѕРІ РёР»Рё РѕР±СЉРµРєС‚РѕРј СЃ РєР»СЋС‡РѕРј participants")
        return [_normalize_record(item) for item in payload if isinstance(item, dict)]

    if lower_name.endswith(".csv"):
        text = None
        for enc in ("utf-8-sig", "utf-8", "cp1251"):
            try:
                text = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("Р СњР Вµ РЎС“Р Т‘Р В°Р В»Р С•РЎРѓРЎРЉ Р Т‘Р ВµР С”Р С•Р Т‘Р С‘РЎР‚Р С•Р Р†Р В°РЎвЂљРЎРЉ CSV. Р ВРЎРѓР С—Р С•Р В»РЎРЉР В·РЎС“Р в„–РЎвЂљР Вµ UTF-8 Р С‘Р В»Р С‘ CP1251")

        reader = csv.DictReader(io.StringIO(text))
        return [_normalize_record(row) for row in reader]

    if lower_name.endswith(".xlsx"):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise ValueError("Р”Р»СЏ РёРјРїРѕСЂС‚Р° XLSX С‚СЂРµР±СѓРµС‚СЃСЏ Р·Р°РІРёСЃРёРјРѕСЃС‚СЊ openpyxl") from exc

        wb = load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [_normalize_header(str(h or "")) for h in rows[0]]
        records: list[dict[str, Any]] = []
        for row in rows[1:]:
            if not any(cell is not None and str(cell).strip() for cell in row):
                continue
            item = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
            records.append(item)
        return records

    raise ValueError("РџРѕРґРґРµСЂР¶РёРІР°СЋС‚СЃСЏ С‚РѕР»СЊРєРѕ С„Р°Р№Р»С‹ .json, .csv, .xlsx")


def _extract_special_tours(competition) -> list[dict[str, Any]]:
    """Extract normalized special tours config from competition settings."""
    allowed_modes = {"individual", "individual_captains", "team"}
    settings_payload = competition.special_settings or {}
    raw_tours = settings_payload.get("tours")

    normalized: list[dict[str, Any]] = []
    if isinstance(raw_tours, list):
        for idx, item in enumerate(raw_tours, start=1):
            if not isinstance(item, dict):
                continue
            tour_number = int(item.get("tour_number") or idx)
            mode = str(item.get("mode") or "individual").strip()
            if mode not in allowed_modes:
                mode = "individual"
            task_numbers = item.get("task_numbers") or item.get("tasks") or [1]
            tasks: list[int] = []
            for t in task_numbers:
                try:
                    val = int(t)
                    if val > 0:
                        tasks.append(val)
                except Exception:  # noqa: BLE001
                    continue
            if not tasks:
                tasks = [1]
            normalized.append(
                {
                    "tour_number": tour_number,
                    "mode": mode,
                    "task_numbers": sorted(set(tasks)),
                }
            )

    if normalized:
        return normalized

    tours_count = int(competition.special_tours_count or 1)
    modes = competition.special_tour_modes or []
    fallback: list[dict[str, Any]] = []
    for i in range(tours_count):
        mode = modes[i] if i < len(modes) else "individual"
        if mode not in allowed_modes:
            mode = "individual"
        fallback.append(
            {
                "tour_number": i + 1,
                "mode": mode,
                "task_numbers": [1],
            }
        )
    return fallback


def _resolve_default_seat_matrix_columns(competition) -> int:
    settings_payload = competition.special_settings or {}
    raw_value = settings_payload.get("seat_matrix_columns", 3)
    try:
        columns = int(raw_value)
    except (TypeError, ValueError):
        columns = 3
    return max(columns, 1)


def _resolve_room_seat_matrix_columns(competition, room_id: UUID, is_team_mode: bool) -> int:
    settings_payload = (competition.special_settings or {}) if competition else {}
    room_key = str(room_id)

    def _extract_from_map(mapping: Any) -> int | None:
        if not isinstance(mapping, dict):
            return None
        room_payload = mapping.get(room_key)
        if not isinstance(room_payload, dict):
            return None
        raw_value = room_payload.get("seat_matrix_columns")
        try:
            parsed = int(raw_value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    room_layouts = settings_payload.get("room_layouts")
    team_room_layouts = settings_payload.get("team_room_layouts")
    selected = _extract_from_map(team_room_layouts if is_team_mode else room_layouts)
    if selected is None and is_team_mode:
        selected = _extract_from_map(room_layouts)
    if selected is None:
        selected = _resolve_default_seat_matrix_columns(competition)
    return max(int(selected), 1)


def _resolve_room_team_table_merges(competition, room_id: UUID, tour_number: int | None) -> list[list[int]]:
    if not competition or tour_number is None:
        return []

    settings_payload = competition.special_settings or {}
    raw_merges = settings_payload.get("team_table_merges")
    if not isinstance(raw_merges, dict):
        return []

    tour_payload = raw_merges.get(str(tour_number))
    if tour_payload is None:
        tour_payload = raw_merges.get(tour_number)
    if not isinstance(tour_payload, dict):
        return []

    room_payload = tour_payload.get(str(room_id))
    if not isinstance(room_payload, list):
        return []

    normalized: list[list[int]] = []
    used_tables: set[int] = set()
    for group in room_payload:
        if not isinstance(group, list):
            continue
        group_values = sorted({int(v) for v in group if isinstance(v, int) and int(v) > 0})
        if len(group_values) < 2:
            continue
        if any(v in used_tables for v in group_values):
            continue
        used_tables.update(group_values)
        normalized.append(group_values)
    return normalized


def _resolve_special_tour_context(competition, tour_number: int | None) -> dict[str, Any] | None:
    if not competition or not getattr(competition, "is_special", False):
        return None

    tours = _extract_special_tours(competition)
    if not tours:
        return None

    if tour_number is None:
        selected = tours[0]
    else:
        selected = next((item for item in tours if int(item.get("tour_number", 0)) == tour_number), None)
        if not selected:
            raise HTTPException(status_code=400, detail="РЈРєР°Р·Р°РЅ РЅРµСЃСѓС‰РµСЃС‚РІСѓСЋС‰РёР№ РЅРѕРјРµСЂ С‚СѓСЂР°")

    mode = str(selected.get("mode") or "individual").strip()
    return {
        "tour_number": int(selected.get("tour_number") or 1),
        "mode": mode,
        "is_team_mode": mode == "team",
    }


def _resolve_room_seats_per_table(competition, room_id: UUID, is_team_mode: bool) -> int:
    settings_payload = (competition.special_settings or {}) if competition else {}
    room_key = str(room_id)

    def _extract_from_map(mapping: Any) -> int | None:
        if not isinstance(mapping, dict):
            return None
        room_payload = mapping.get(room_key)
        if not isinstance(room_payload, dict):
            return None
        raw_value = room_payload.get("seats_per_table")
        try:
            parsed = int(raw_value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    room_layouts = settings_payload.get("room_layouts")
    team_room_layouts = settings_payload.get("team_room_layouts")
    selected = _extract_from_map(team_room_layouts if is_team_mode else room_layouts)
    if selected is None and is_team_mode:
        selected = _extract_from_map(room_layouts)

    if selected is None:
        raw_default = (
            settings_payload.get("team_default_seats_per_table")
            if is_team_mode
            else settings_payload.get("default_seats_per_table")
        )
        try:
            selected = int(raw_default)
        except (TypeError, ValueError):
            selected = 1

    return max(int(selected), 1)


def _build_room_tables(
    room_capacity: int,
    seats_by_number: dict[int, dict[str, Any]],
    seats_per_table: int,
) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    tables_count = (room_capacity + seats_per_table - 1) // seats_per_table
    for table_number in range(1, tables_count + 1):
        table_seats: list[dict[str, Any]] = []
        base = (table_number - 1) * seats_per_table
        for seat_at_table in range(1, seats_per_table + 1):
            seat_number = base + seat_at_table
            if seat_number > room_capacity:
                break
            seat_data = seats_by_number.get(seat_number)
            table_seats.append(
                {
                    "seat_number": seat_number,
                    "seat_at_table": seat_at_table,
                    "table_number": table_number,
                    "occupied": seat_data is not None,
                    "variant_number": seat_data["variant_number"] if seat_data else None,
                    "participant_name": seat_data["participant_name"] if seat_data else None,
                    "institution_id": seat_data["institution_id"] if seat_data else None,
                    "institution_name": seat_data["institution_name"] if seat_data else None,
                    "institution_location": seat_data["institution_location"] if seat_data else None,
                    "is_captain": seat_data["is_captain"] if seat_data else False,
                }
            )
        if table_seats:
            tables.append(
                {
                    "table_number": table_number,
                    "occupied": any(seat["occupied"] for seat in table_seats),
                    "seats": table_seats,
                }
            )
    return tables


def _annotate_tables_with_merges(room_tables: list[dict[str, Any]], merge_groups: list[list[int]]) -> list[list[int]]:
    if not room_tables:
        return []

    table_numbers = {int(table.get("table_number", 0)) for table in room_tables}
    valid_groups: list[list[int]] = []
    table_to_group: dict[int, int] = {}

    for group in merge_groups:
        valid_group = sorted(table for table in group if table in table_numbers)
        if len(valid_group) < 2:
            continue
        group_id = len(valid_groups) + 1
        valid_groups.append(valid_group)
        for table_number in valid_group:
            table_to_group[table_number] = group_id

    for table in room_tables:
        table_number = int(table.get("table_number", 0))
        group_id = table_to_group.get(table_number)
        table["merged_group"] = group_id
        table["merged_with"] = (
            [n for n in valid_groups[group_id - 1] if n != table_number]
            if group_id
            else []
        )

    return valid_groups


def _project_team_seating_for_merges(
    room_tables: list[dict[str, Any]],
    merge_groups: list[list[int]],
) -> None:
    """Rebuild room table occupancy for team mode so merged groups hold one team when possible.

    This is a view-layer projection for team seating plan rendering (does not persist to DB).
    """
    if not room_tables:
        return

    table_by_number: dict[int, dict[str, Any]] = {
        int(table.get("table_number", 0)): table
        for table in room_tables
        if int(table.get("table_number", 0)) > 0
    }
    if not table_by_number:
        return

    valid_groups: list[list[int]] = []
    merged_table_numbers: set[int] = set()
    for group in merge_groups:
        numbers = sorted({int(number) for number in group if int(number) in table_by_number})
        if len(numbers) < 2:
            continue
        valid_groups.append(numbers)
        merged_table_numbers.update(numbers)

    # Collect currently seated participants and group by institution (team).
    team_buckets: dict[str, list[dict[str, Any]]] = {}
    for table in room_tables:
        for seat in table.get("seats", []):
            if not seat.get("occupied"):
                continue
            institution_id = seat.get("institution_id")
            institution_name = (seat.get("institution_name") or "").strip()
            if institution_id:
                team_key = f"id:{institution_id}"
            elif institution_name:
                team_key = f"name:{institution_name.lower()}"
            else:
                team_key = f"solo:{seat.get('participant_name') or seat.get('seat_number')}"

            team_buckets.setdefault(team_key, []).append(
                {
                    "occupied": True,
                    "variant_number": seat.get("variant_number"),
                    "participant_name": seat.get("participant_name"),
                    "institution_id": seat.get("institution_id"),
                    "institution_name": seat.get("institution_name"),
                    "institution_location": seat.get("institution_location"),
                    "is_captain": bool(seat.get("is_captain")),
                }
            )

    def _active_team_keys() -> list[str]:
        return sorted(
            (key for key, bucket in team_buckets.items() if bucket),
            key=lambda key: (-len(team_buckets[key]), key),
        )

    def _take_from_team(team_key: str, count: int) -> list[dict[str, Any]]:
        if count <= 0:
            return []
        bucket = team_buckets.get(team_key) or []
        taken = bucket[:count]
        team_buckets[team_key] = bucket[count:]
        return taken

    def _empty_seat_payload() -> dict[str, Any]:
        return {
            "occupied": False,
            "variant_number": None,
            "participant_name": None,
            "institution_id": None,
            "institution_name": None,
            "institution_location": None,
            "is_captain": False,
        }

    # Reset all seats first.
    for table in room_tables:
        for seat in table.get("seats", []):
            seat.update(_empty_seat_payload())

    def _slots_for_table_number(table_number: int) -> list[dict[str, Any]]:
        table = table_by_number.get(table_number)
        if not table:
            return []
        return sorted(
            list(table.get("seats", [])),
            key=lambda seat: (int(seat.get("seat_at_table") or 0), int(seat.get("seat_number") or 0)),
        )

    def _assign_to_slots(slots: list[dict[str, Any]], payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for slot, payload in zip(slots, payloads):
            slot.update(payload)
        return slots[len(payloads):]

    merged_overflow_slots: list[dict[str, Any]] = []

    # Pass 1: each merged block gets one team whenever possible.
    for group in valid_groups:
        slots: list[dict[str, Any]] = []
        for table_number in group:
            slots.extend(_slots_for_table_number(table_number))
        if not slots:
            continue
        keys = _active_team_keys()
        if not keys:
            merged_overflow_slots.extend(slots)
            continue
        chosen_team = keys[0]
        assigned = _take_from_team(chosen_team, len(slots))
        remaining = _assign_to_slots(slots, assigned)
        merged_overflow_slots.extend(remaining)

    # Pass 2: fill non-merged tables from remaining teams.
    non_merged_numbers = sorted(number for number in table_by_number if number not in merged_table_numbers)
    for table_number in non_merged_numbers:
        slots = _slots_for_table_number(table_number)
        slot_index = 0
        while slot_index < len(slots):
            keys = _active_team_keys()
            if not keys:
                break
            chosen_team = keys[0]
            take_count = min(len(slots) - slot_index, len(team_buckets[chosen_team]))
            assigned = _take_from_team(chosen_team, take_count)
            remaining = _assign_to_slots(slots[slot_index : slot_index + take_count], assigned)
            slot_index += take_count - len(remaining)

    # Pass 3: if participants still remain, place them into free slots inside merged blocks.
    for slot in merged_overflow_slots:
        keys = _active_team_keys()
        if not keys:
            break
        chosen_team = keys[0]
        assigned = _take_from_team(chosen_team, 1)
        if not assigned:
            continue
        slot.update(assigned[0])

    for table in room_tables:
        table["occupied"] = any(bool(seat.get("occupied")) for seat in table.get("seats", []))


# --- User Management ---

@router.get("/users", response_model=UserListResponse)
async def list_users(
    skip: int = 0,
    limit: int = 50,
    role: Optional[UserRole] = None,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """List all users with optional role filter."""
    user_repo = UserRepositoryImpl(db)

    if role:
        users = await user_repo.get_by_role(role, skip=skip, limit=limit)
    else:
        users = await user_repo.get_all(skip=skip, limit=limit)

    items = [
        AdminUserResponse(
            id=u.id,
            email=u.email,
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in users
    ]
    return UserListResponse(items=items, total=len(items))


@router.post("/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
async def create_staff_user(
    body: CreateStaffRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Create a user account (participant / admitter / scanner / admin)."""
    user_repo = UserRepositoryImpl(db)

    if await user_repo.exists_by_email(body.email):
        raise HTTPException(status_code=400, detail="Email СѓР¶Рµ РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ")

    # Validate participant-specific fields
    if body.role == UserRole.PARTICIPANT:
        if not body.full_name or len(body.full_name.strip()) < 2:
            raise HTTPException(status_code=400, detail="Р В¤Р ВР С› Р С•Р В±РЎРЏР В·Р В°РЎвЂљР ВµР В»РЎРЉР Р…Р С• Р Т‘Р В»РЎРЏ РЎС“РЎвЂЎР В°РЎРѓРЎвЂљР Р…Р С‘Р С”Р С•Р Р† (Р СР С‘Р Р…Р С‘Р СРЎС“Р С 2 РЎРѓР С‘Р СР Р†Р С•Р В»Р В°)")
        if not body.school or len(body.school.strip()) < 2:
            raise HTTPException(status_code=400, detail="РЈС‡РµР±РЅРѕРµ СѓС‡СЂРµР¶РґРµРЅРёРµ РѕР±СЏР·Р°С‚РµР»СЊРЅРѕ РґР»СЏ СѓС‡Р°СЃС‚РЅРёРєРѕРІ (РјРёРЅРёРјСѓРј 2 СЃРёРјРІРѕР»Р°)")

    from uuid import uuid4

    user = User(
        id=uuid4(),
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    user = await user_repo.create(user)

    # Create participant profile if role is participant
    if body.role == UserRole.PARTICIPANT:
        from ....domain.entities import Participant
        participant_repo = ParticipantRepositoryImpl(db)

        participant = Participant(
            id=uuid4(),
            user_id=user.id,
            full_name=body.full_name,
            school=body.school,
            grade=body.grade,
            institution_id=body.institution_id,
            institution_location=body.institution_location,
            is_captain=body.is_captain,
            dob=body.dob,
        )
        await participant_repo.create(participant)

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.put("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: UUID,
    body: UpdateUserRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Update user attributes (active status, role)."""
    user_repo = UserRepositoryImpl(db)
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ")

    if body.is_active is not None:
        if body.is_active:
            user.activate()
        else:
            user.deactivate()

    if body.role is not None:
        user.change_role(body.role)

    await user_repo.update(user)

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: UUID,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a user (soft delete)."""
    user_repo = UserRepositoryImpl(db)
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="РќРµР»СЊР·СЏ РґРµР°РєС‚РёРІРёСЂРѕРІР°С‚СЊ СЃРµР±СЏ")

    user.deactivate()
    await user_repo.update(user)


# --- Participants ---

@router.get("/participants")
async def list_participants(
    skip: int = 0,
    limit: int = 1000,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """List all participants (id, full_name, school) for admin registration."""
    from ....infrastructure.database.models import ParticipantModel

    stmt = (
        select(ParticipantModel)
        .order_by(ParticipantModel.full_name)
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    participants = result.scalars().all()

    return {
        "participants": [
            {
                "id": str(p.id),
                "user_id": str(p.user_id),
                "full_name": p.full_name,
                "school": p.school,
                "institution_location": p.institution_location,
                "is_captain": p.is_captain,
            }
            for p in participants
        ]
    }


# --- Audit Log ---

@router.get("/audit-log", response_model=AuditLogListResponse)
async def list_audit_log(
    skip: int = 0,
    limit: int = 50,
    entity_type: Optional[str] = None,
    entity_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """List audit log entries with optional filters."""
    audit_repo = AuditLogRepositoryImpl(db)

    if entity_type and entity_id:
        logs = await audit_repo.get_by_entity(entity_type, entity_id, skip=skip, limit=limit)
    elif user_id:
        logs = await audit_repo.get_by_user(user_id, skip=skip, limit=limit)
    else:
        logs = await audit_repo.get_all(skip=skip, limit=limit)

    items = [
        AuditLogEntry(
            id=log.id,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            action=log.action,
            user_id=log.user_id,
            ip_address=log.ip_address,
            details=log.details,
            timestamp=log.timestamp,
        )
        for log in logs
    ]
    return AuditLogListResponse(items=items, total=len(items))


# --- Statistics ---

@router.get("/statistics", response_model=StatisticsResponse)
async def get_statistics(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Get system statistics for admin dashboard."""
    from sqlalchemy import select, func
    from ....infrastructure.database.models import (
        UserModel,
        CompetitionModel,
        ScanModel,
        RegistrationModel,
        ParticipantModel,
    )

    # Count users
    result = await db.execute(select(func.count()).select_from(UserModel))
    total_users = result.scalar() or 0

    # Count competitions
    result = await db.execute(select(func.count()).select_from(CompetitionModel))
    total_competitions = result.scalar() or 0

    # Count scans
    result = await db.execute(select(func.count()).select_from(ScanModel))
    total_scans = result.scalar() or 0

    # Count registrations
    result = await db.execute(select(func.count()).select_from(RegistrationModel))
    total_registrations = result.scalar() or 0

    # Count participants
    result = await db.execute(select(func.count()).select_from(ParticipantModel))
    total_participants = result.scalar() or 0

    return StatisticsResponse(
        total_competitions=total_competitions,
        total_users=total_users,
        total_scans=total_scans,
        total_registrations=total_registrations,
        total_participants=total_participants,
    )


# --- Registration Management ---

@router.post("/registrations", response_model=AdminRegisterResponse, status_code=status.HTTP_201_CREATED)
async def admin_register_participant(
    body: AdminRegisterRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Admin registers a participant for a competition (bypasses status check)."""
    registration_repo = RegistrationRepositoryImpl(db)
    competition_repo = CompetitionRepositoryImpl(db)
    participant_repo = ParticipantRepositoryImpl(db)
    entry_token_repo = EntryTokenRepositoryImpl(db)
    token_service = TokenService()

    use_case = RegisterForCompetitionUseCase(
        registration_repository=registration_repo,
        competition_repository=competition_repo,
        participant_repository=participant_repo,
        entry_token_repository=entry_token_repo,
        token_service=token_service,
    )

    try:
        result = await use_case.execute(
            participant_id=body.participant_id,
            competition_id=body.competition_id,
            skip_status_check=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return AdminRegisterResponse(
        registration_id=result.registration_id,
        entry_token=result.entry_token,
    )


@router.get("/registrations/{competition_id}", response_model=AdminRegistrationListResponse)
async def list_competition_registrations(
    competition_id: UUID,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """List all registrations for a competition with participant details."""
    from ....infrastructure.database.models import (
        RegistrationModel,
        ParticipantModel,
        EntryTokenModel,
        InstitutionModel,
    )

    stmt = (
        select(RegistrationModel)
        .where(RegistrationModel.competition_id == competition_id)
        .options(
            selectinload(RegistrationModel.entry_token),
            selectinload(RegistrationModel.participant).selectinload(ParticipantModel.institution),
        )
        .order_by(RegistrationModel.created_at)
    )
    result = await db.execute(stmt)
    registrations = result.scalars().all()

    items = []
    for reg in registrations:
        participant = reg.participant
        institution_name = None
        if participant and participant.institution:
            institution_name = participant.institution.name

        entry_token_raw = None
        if reg.entry_token:
            entry_token_raw = reg.entry_token.raw_token

        items.append(
            AdminRegistrationItem(
                registration_id=reg.id,
                participant_id=reg.participant_id,
                participant_name=participant.full_name if participant else "вЂ”",
                participant_school=participant.school if participant else "вЂ”",
                participant_institution_location=participant.institution_location if participant else None,
                participant_is_captain=participant.is_captain if participant else False,
                institution_name=institution_name,
                entry_token=entry_token_raw,
                status=reg.status.value,
            )
        )

    return AdminRegistrationListResponse(items=items, total=len(items))


@router.get("/registrations/{competition_id}/badges-pdf")
async def download_badges_pdf(
    competition_id: UUID,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Download a PDF with QR badges for all registrations, grouped by institution."""
    from ....infrastructure.database.models import (
        RegistrationModel,
        CompetitionModel,
    )
    from ....infrastructure.pdf.badge_generator import BadgeGenerator, BadgeData
    from io import BytesIO

    # Get competition name
    comp_result = await db.execute(
        select(CompetitionModel).where(CompetitionModel.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    if not competition:
        raise HTTPException(status_code=404, detail="РћР»РёРјРїРёР°РґР° РЅРµ РЅР°Р№РґРµРЅР°")

    # Get registrations
    from ....infrastructure.database.models import ParticipantModel
    stmt = (
        select(RegistrationModel)
        .where(RegistrationModel.competition_id == competition_id)
        .options(
            selectinload(RegistrationModel.entry_token),
            selectinload(RegistrationModel.participant).selectinload(ParticipantModel.institution),
        )
        .order_by(RegistrationModel.created_at)
    )
    result = await db.execute(stmt)
    registrations = result.scalars().all()

    badges: list[BadgeData] = []
    for reg in registrations:
        participant = reg.participant
        if not participant:
            continue

        entry_token_raw = None
        if reg.entry_token and reg.entry_token.raw_token:
            entry_token_raw = reg.entry_token.raw_token

        if not entry_token_raw:
            continue

        institution_name = ""
        if participant.institution:
            institution_name = participant.institution.name

        badges.append(
            BadgeData(
                name=participant.full_name,
                school=participant.school,
                institution=institution_name,
                qr_token=entry_token_raw,
            )
        )

    # Sort by institution then name
    badges.sort(key=lambda b: (b.institution or "", b.name))

    generator = BadgeGenerator()
    pdf_bytes = generator.generate_badges_pdf(competition.name, badges)

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="badges_{competition_id}.pdf"'
        },
    )


@router.get("/competitions/{competition_id}/seating-plan")
async def get_seating_plan(
    competition_id: UUID,
    tour_number: int | None = Query(None, ge=1, description="Tour number for special seating mode"),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.ADMITTER, UserRole.INVIGILATOR)),
    db: AsyncSession = Depends(get_db),
):
    """Get seating plan grouped by room for viewing/printing."""
    from ....infrastructure.database.models import (
        CompetitionModel,
        RoomModel,
        SeatAssignmentModel,
        RegistrationModel,
        ParticipantModel,
        InstitutionModel,
    )

    competition_result = await db.execute(
        select(CompetitionModel).where(CompetitionModel.id == competition_id)
    )
    competition = competition_result.scalar_one_or_none()
    if not competition:
        raise HTTPException(status_code=404, detail="РћР»РёРјРїРёР°РґР° РЅРµ РЅР°Р№РґРµРЅР°")

    default_seat_matrix_columns = _resolve_default_seat_matrix_columns(competition)
    special_tour_context = _resolve_special_tour_context(competition, tour_number=tour_number)
    is_team_mode = bool(special_tour_context and special_tour_context["is_team_mode"])
    selected_tour_number = int(special_tour_context["tour_number"]) if special_tour_context else None

    rooms_result = await db.execute(
        select(RoomModel)
        .where(RoomModel.competition_id == competition_id)
        .order_by(RoomModel.name.asc())
    )
    rooms = rooms_result.scalars().all()

    plan_rooms: list[dict[str, Any]] = []
    for room in rooms:
        seats_result = await db.execute(
            select(
                SeatAssignmentModel.seat_number,
                SeatAssignmentModel.variant_number,
                ParticipantModel.full_name,
                ParticipantModel.institution_id,
                ParticipantModel.institution_location,
                ParticipantModel.is_captain,
                InstitutionModel.name.label("institution_name"),
            )
            .join(RegistrationModel, RegistrationModel.id == SeatAssignmentModel.registration_id)
            .join(ParticipantModel, ParticipantModel.id == RegistrationModel.participant_id)
            .outerjoin(InstitutionModel, InstitutionModel.id == ParticipantModel.institution_id)
            .where(SeatAssignmentModel.room_id == room.id)
            .order_by(SeatAssignmentModel.seat_number.asc())
        )
        seat_rows = seats_result.all()
        seats = [
            {
                "seat_number": row.seat_number,
                "variant_number": row.variant_number,
                "participant_name": row.full_name,
                "institution_id": row.institution_id,
                "institution_name": row.institution_name,
                "institution_location": row.institution_location,
                "is_captain": row.is_captain,
            }
            for row in seat_rows
        ]
        seats_by_number = {seat["seat_number"]: seat for seat in seats}
        seats_per_table = _resolve_room_seats_per_table(
            competition=competition,
            room_id=room.id,
            is_team_mode=is_team_mode,
        )
        room_seat_matrix_columns = _resolve_room_seat_matrix_columns(
            competition=competition,
            room_id=room.id,
            is_team_mode=is_team_mode,
        )
        room_tables = _build_room_tables(
            room_capacity=room.capacity,
            seats_by_number=seats_by_number,
            seats_per_table=seats_per_table,
        )
        merge_groups = _resolve_room_team_table_merges(
            competition=competition,
            room_id=room.id,
            tour_number=selected_tour_number if is_team_mode else None,
        )
        normalized_merge_groups = _annotate_tables_with_merges(room_tables, merge_groups)
        if is_team_mode and normalized_merge_groups:
            _project_team_seating_for_merges(room_tables, normalized_merge_groups)
            projected_seats = [
                seat
                for table in room_tables
                for seat in table.get("seats", [])
                if seat.get("occupied")
            ]
            seats = sorted(projected_seats, key=lambda seat: int(seat.get("seat_number") or 0))
            seats_by_number = {seat["seat_number"]: seat for seat in seats}

        matrix_rows_count = (room.capacity + room_seat_matrix_columns - 1) // room_seat_matrix_columns
        seat_matrix: list[list[dict[str, Any]]] = []
        for matrix_row in range(matrix_rows_count):
            row_cells: list[dict[str, Any]] = []
            for matrix_col in range(room_seat_matrix_columns):
                seat_number = matrix_row * room_seat_matrix_columns + matrix_col + 1
                if seat_number > room.capacity:
                    continue
                seat_data = seats_by_number.get(seat_number)
                row_cells.append(
                    {
                        "seat_number": seat_number,
                        "table_number": ((seat_number - 1) // seats_per_table) + 1,
                        "seat_at_table": ((seat_number - 1) % seats_per_table) + 1,
                        "occupied": seat_data is not None,
                        "variant_number": seat_data["variant_number"] if seat_data else None,
                        "participant_name": seat_data["participant_name"] if seat_data else None,
                        "institution_id": seat_data["institution_id"] if seat_data else None,
                        "institution_name": seat_data["institution_name"] if seat_data else None,
                        "institution_location": seat_data["institution_location"] if seat_data else None,
                        "is_captain": seat_data["is_captain"] if seat_data else False,
                    }
                )
            if row_cells:
                seat_matrix.append(row_cells)

        plan_rooms.append(
            {
                "room_id": str(room.id),
                "room_name": room.name,
                "capacity": room.capacity,
                "occupied": len(seats),
                "seat_matrix_columns": room_seat_matrix_columns,
                "seats_per_table": seats_per_table,
                "tables_count": len(room_tables),
                "occupied_tables": sum(1 for table in room_tables if table["occupied"]),
                "table_merges": normalized_merge_groups,
                "has_table_merges": bool(normalized_merge_groups),
                "tables": room_tables,
                "seat_matrix": seat_matrix,
                "seats": seats,
            }
        )

    return {
        "competition_id": str(competition.id),
        "competition_name": competition.name,
        "tour_number": special_tour_context["tour_number"] if special_tour_context else None,
        "tour_mode": special_tour_context["mode"] if special_tour_context else None,
        "is_team_mode": is_team_mode,
        "seat_matrix_columns": default_seat_matrix_columns,
        "rooms": plan_rooms,
    }


@router.get("/competitions/{competition_id}/seating-plan/print", response_class=HTMLResponse)
async def print_seating_plan(
    competition_id: UUID,
    tour_number: int | None = Query(None, ge=1, description="Tour number for special seating mode"),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.ADMITTER, UserRole.INVIGILATOR)),
    db: AsyncSession = Depends(get_db),
):
    """Render printable seating plan as HTML."""
    seating = await get_seating_plan(
        competition_id=competition_id,
        tour_number=tour_number,
        current_user=current_user,
        db=db,
    )

    mode_label_map = {
        "individual": "Индивидуальный",
        "individual_captains": "Индивидуальный (капитаны)",
        "team": "Командный",
    }
    mode_label = mode_label_map.get(seating.get("tour_mode"), seating.get("tour_mode") or "-")

    def esc(value: Any, fallback: str = "-") -> str:
        if value is None:
            return fallback
        text = str(value).strip()
        if not text:
            return fallback
        return escape(text)

    room_sections: list[str] = []
    for room in seating["rooms"]:
        tables = room.get("tables") or []
        table_by_number: dict[int, dict[str, Any]] = {
            int(table.get("table_number", 0)): table
            for table in tables
            if int(table.get("table_number", 0)) > 0
        }
        table_numbers = sorted(table_by_number.keys())
        tables_count = len(table_numbers)

        # Horizontal columns: if config says 3, we render 3 desk columns.
        desk_cols = max(int(room.get("seat_matrix_columns", seating.get("seat_matrix_columns", 3))), 1)
        desk_rows = max((tables_count + desk_cols - 1) // desk_cols, 1)

        def _table_position(table_number: int) -> tuple[int, int]:
            index = table_number - 1
            row = (index // desk_cols) + 1
            col = (index % desk_cols) + 1
            return row, col

        def _render_half(seats: list[dict[str, Any]]) -> str:
            if not seats:
                return "<div class='seat-card empty'>Свободно</div>"

            seat_cards: list[str] = []
            for seat in seats:
                if not seat.get("occupied"):
                    seat_cards.append("<div class='seat-card empty'>Свободно</div>")
                    continue
                captain_badge = "<div class='seat-flag'>Капитан</div>" if seat.get("is_captain") else ""
                seat_cards.append(
                    "<div class='seat-card'>"
                    f"<div class='seat-name'>{esc(seat.get('participant_name'))}</div>"
                    f"<div class='seat-meta'>Место {esc(seat.get('seat_number'))} | Вариант {esc(seat.get('variant_number'))}</div>"
                    f"<div class='seat-meta'>{esc(seat.get('institution_location'))}</div>"
                    f"{captain_badge}"
                    "</div>"
                )
            return "".join(seat_cards)

        def _render_table_inner(table: dict[str, Any], title_prefix: str = "Стол") -> str:
            seats = sorted(
                table.get("seats", []),
                key=lambda s: int(s.get("seat_at_table") or 0),
            )
            if not seats:
                left_half: list[dict[str, Any]] = []
                right_half: list[dict[str, Any]] = []
            else:
                split_index = max((len(seats) + 1) // 2, 1)
                left_half = seats[:split_index]
                right_half = seats[split_index:]
            return (
                f"<div class='desk-head'>{title_prefix} {table.get('table_number')}</div>"
                "<div class='desk-split'>"
                f"<div class='desk-half'>{_render_half(left_half)}</div>"
                f"<div class='desk-half'>{_render_half(right_half)}</div>"
                "</div>"
            )

        normalized_groups: list[list[int]] = []
        for raw_group in (room.get("table_merges") or []):
            if not isinstance(raw_group, list):
                continue
            group = sorted({int(num) for num in raw_group if int(num) in table_by_number})
            if len(group) >= 2:
                normalized_groups.append(group)

        rendered_tables: set[int] = set()
        desk_blocks: list[str] = []
        invalid_merges: list[str] = []

        for group in normalized_groups:
            positions = [(num, *_table_position(num)) for num in group]
            rows = sorted({row for _, row, _ in positions})
            cols = sorted({col for _, _, col in positions})

            is_horizontal_chain = (
                len(rows) == 1
                and cols == list(range(min(cols), max(cols) + 1))
                and len(cols) == len(group)
            )
            is_vertical_chain = (
                len(cols) == 1
                and rows == list(range(min(rows), max(rows) + 1))
                and len(rows) == len(group)
            )

            if not (is_horizontal_chain or is_vertical_chain):
                invalid_merges.append("+".join(str(num) for num in group))
                continue

            if is_horizontal_chain:
                row_start = rows[0]
                col_start = min(cols)
                col_span = len(cols)
                grid_style = f"grid-column:{col_start} / span {col_span};grid-row:{row_start};"
                stack_class = "merged-stack horizontal"
            else:
                col_start = cols[0]
                row_start = min(rows)
                row_span = len(rows)
                grid_style = f"grid-column:{col_start};grid-row:{row_start} / span {row_span};"
                stack_class = "merged-stack vertical"

            grouped_tables = [table_by_number[num] for num in group]
            seats_total = sum(len(table.get("seats", [])) for table in grouped_tables)
            occupied_total = sum(
                1
                for table in grouped_tables
                for seat in table.get("seats", [])
                if seat.get("occupied")
            )
            merged_label = "+".join(str(num) for num in group)
            merged_state = "occupied" if occupied_total else "free"
            merged_cards = "".join(
                f"<div class='merged-table-card'>{_render_table_inner(table_by_number[num])}</div>"
                for num in group
            )
            desk_blocks.append(
                f"<div class='desk merged {merged_state}' style='{grid_style}'>"
                f"<div class='desk-merge-title'>Столы {merged_label} ({occupied_total}/{seats_total})</div>"
                f"<div class='{stack_class}'>{merged_cards}</div>"
                "</div>"
            )
            rendered_tables.update(group)

        for table_number in table_numbers:
            if table_number in rendered_tables:
                continue
            table = table_by_number[table_number]
            row, col = _table_position(table_number)
            state = "occupied" if any(seat.get("occupied") for seat in table.get("seats", [])) else "free"
            desk_blocks.append(
                f"<div class='desk {state}' style='grid-column:{col};grid-row:{row};'>"
                f"{_render_table_inner(table)}"
                "</div>"
            )

        auditorium_html = (
            "<div class='auditorium'>"
            f"<div class='room-center'>{esc(room['room_name'], fallback='')}</div>"
            f"<div class='auditorium-grid' style='--aud-rows:{desk_rows};--aud-cols:{desk_cols};'>"
            f"{''.join(desk_blocks) or '<div class=\"no-desks\">Нет столов</div>'}"
            "</div>"
            "</div>"
        )

        rows_html: list[str] = []
        for seat in room["seats"]:
            rows_html.append(
                "<tr>"
                f"<td>{seat['seat_number']}</td>"
                f"<td>{esc(seat['participant_name'])}</td>"
                f"<td>{esc(seat.get('institution_name'))}</td>"
                f"<td>{esc(seat.get('institution_location'))}</td>"
                f"<td>{'Да' if seat.get('is_captain') else 'Нет'}</td>"
                f"<td>{esc(seat.get('variant_number'))}</td>"
                "</tr>"
            )

        table_html = (
            "<table>"
            "<thead><tr>"
            "<th>Место</th><th>Участник</th><th>Учреждение</th><th>Город/филиал</th><th>Капитан</th><th>Вариант</th>"
            "</tr></thead>"
            f"<tbody>{''.join(rows_html) or '<tr><td colspan=\"6\">Нет рассадки</td></tr>'}</tbody>"
            "</table>"
        )

        merges_text = ", ".join("+".join(str(table_number) for table_number in group) for group in normalized_groups)
        merges_line = f"<div class='muted'>Объединения столов: {escape(merges_text)}</div>" if merges_text else ""
        invalid_merges_line = (
            f"<div class='merge-warning'>Не удалось отрисовать объединение для групп: {escape(', '.join(invalid_merges))}</div>"
            if invalid_merges
            else ""
        )

        room_sections.append(
            "<section>"
            f"<h2>{esc(room['room_name'], fallback='Аудитория')} ({room['occupied']}/{room['capacity']})</h2>"
            f"<div class='muted'>Колонок столов: {desk_cols} | Рядов столов: {desk_rows}</div>"
            f"<div class='muted'>Мест за столом: {room.get('seats_per_table', 1)} | Столов: {room.get('tables_count', 0)} (занято {room.get('occupied_tables', 0)})</div>"
            f"{merges_line}"
            f"{invalid_merges_line}"
            f"{auditorium_html}"
            f"{table_html}"
            "</section>"
        )

    html = (
        "<!doctype html>"
        "<html><head><meta charset='utf-8'>"
        f"<title>Схема рассадки - {esc(seating['competition_name'])}</title>"
        "<style>"
        "body{font-family:Arial,sans-serif;margin:24px;color:#111;}"
        "h1{margin-bottom:8px;} h2{margin-top:26px;margin-bottom:6px;}"
        ".muted{color:#5f6368;font-size:12px;}"
        ".merge-warning{margin-top:4px;color:#b3261e;font-size:12px;}"
        ".auditorium{position:relative;border:2px solid #202124;border-radius:10px;margin-top:12px;padding:16px;background:linear-gradient(180deg,#ffffff 0%,#f8f9fa 100%);min-height:300px;}"
        ".room-center{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:34px;font-weight:700;color:rgba(95,99,104,.25);pointer-events:none;letter-spacing:1px;text-transform:uppercase;}"
        ".auditorium-grid{position:relative;z-index:1;display:grid;grid-template-columns:repeat(var(--aud-cols),minmax(95px,1fr));grid-template-rows:repeat(var(--aud-rows),minmax(58px,1fr));gap:10px;min-height:260px;}"
        ".desk{border:1.5px solid #5f6368;border-radius:8px;padding:6px;background:#fff;display:flex;flex-direction:column;gap:6px;line-height:1.25;}"
        ".desk.occupied{background:#e8f0fe;border-color:#1a73e8;}"
        ".desk.free{background:#f8f9fa;border-color:#9aa0a6;}"
        ".desk.merged{border-width:2.5px;background:#e6f4ea;border-color:#137333;padding:8px;}"
        ".desk-merge-title{font-size:12px;font-weight:700;text-align:center;}"
        ".merged-stack{display:flex;gap:0;align-items:stretch;}"
        ".merged-stack.vertical{flex-direction:column;}"
        ".merged-stack.horizontal{flex-direction:row;}"
        ".merged-table-card{border:1px solid #7aa786;border-radius:0;padding:4px;background:#fff;flex:1 1 0;}"
        ".merged-stack.horizontal .merged-table-card + .merged-table-card{margin-left:-1px;}"
        ".merged-stack.vertical .merged-table-card + .merged-table-card{margin-top:-1px;}"
        ".merged-stack.horizontal .merged-table-card:first-child{border-top-left-radius:6px;border-bottom-left-radius:6px;}"
        ".merged-stack.horizontal .merged-table-card:last-child{border-top-right-radius:6px;border-bottom-right-radius:6px;}"
        ".merged-stack.vertical .merged-table-card:first-child{border-top-left-radius:6px;border-top-right-radius:6px;}"
        ".merged-stack.vertical .merged-table-card:last-child{border-bottom-left-radius:6px;border-bottom-right-radius:6px;}"
        ".desk-head{font-size:12px;font-weight:700;text-align:center;margin-bottom:4px;}"
        ".desk-split{display:grid;grid-template-columns:1fr 1fr;border:1px solid #9aa0a6;border-radius:6px;overflow:hidden;background:#fff;}"
        ".desk-half{min-height:74px;padding:4px;display:flex;flex-direction:column;justify-content:flex-start;}"
        ".desk-half + .desk-half{border-left:1px solid #9aa0a6;}"
        ".seat-card{font-size:10px;padding:2px 0;border-bottom:1px dashed #d2d6dc;}"
        ".seat-card:last-child{border-bottom:none;}"
        ".seat-card.empty{display:flex;align-items:center;justify-content:center;min-height:18px;color:#6b7280;}"
        ".seat-name{font-weight:700;word-break:break-word;}"
        ".seat-meta{color:#374151;word-break:break-word;}"
        ".seat-flag{display:inline-block;margin-top:2px;font-size:9px;font-weight:700;color:#0b57d0;}"
        ".no-desks{grid-column:1 / -1;display:flex;align-items:center;justify-content:center;color:#5f6368;border:1px dashed #9aa0a6;border-radius:8px;min-height:64px;}"
        "table{border-collapse:collapse;width:100%;margin-top:10px;}"
        "th,td{border:1px solid #c7c7c7;padding:6px 8px;font-size:12px;text-align:left;}"
        "th{background:#f1f3f4;}"
        "@media print{body{margin:0.5cm;} section{break-inside:avoid;page-break-inside:avoid;} .auditorium{break-inside:avoid;}}"
        "</style></head><body>"
        "<h1>Схема рассадки</h1>"
        f"<div><strong>Олимпиада:</strong> {esc(seating['competition_name'])}</div>"
        f"<div class='muted'>Тур: {esc(seating.get('tour_number'))} | Режим: {esc(mode_label)}</div>"
        f"{''.join(room_sections)}"
        "</body></html>"
    )

    return HTMLResponse(content=html)


# --- Special Olympiad ---


@router.get("/special/templates")
async def get_special_templates_info(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Get Word template paths used for special olympiad documents."""
    generator = WordTemplateGenerator()
    paths = generator.get_template_paths()
    return {
        "templates": [
            {"kind": "answer_blank", "path": paths["answer_blank"]},
            {"kind": "a3_cover", "path": paths["a3_cover"]},
        ]
    }


@router.get("/special/templates/{template_kind}/download")
async def download_special_template(
    template_kind: str,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Download current DOCX template."""
    generator = WordTemplateGenerator()
    paths = generator.get_template_paths()

    if template_kind not in paths:
        raise HTTPException(status_code=404, detail="РќРµРёР·РІРµСЃС‚РЅС‹Р№ С‚РёРї С€Р°Р±Р»РѕРЅР°")

    path = paths[template_kind]
    try:
        with open(path, "rb") as f:
            content = f.read()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РєСЂС‹С‚СЊ С€Р°Р±Р»РѕРЅ: {exc}")

    filename = Path(path).name
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'},
    )


@router.post("/special/templates/{template_kind}/upload")
async def upload_special_template(
    template_kind: str,
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Upload replacement DOCX template."""
    generator = WordTemplateGenerator()
    paths = generator.get_template_paths()

    if template_kind not in paths:
        raise HTTPException(status_code=404, detail="РќРµРёР·РІРµСЃС‚РЅС‹Р№ С‚РёРї С€Р°Р±Р»РѕРЅР°")
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="РќСѓР¶РµРЅ С„Р°Р№Р» .docx")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Р¤Р°Р№Р» РїСѓСЃС‚РѕР№")

    path = paths[template_kind]
    try:
        with open(path, "wb") as f:
            f.write(content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕС…СЂР°РЅРёС‚СЊ С€Р°Р±Р»РѕРЅ: {exc}")

    return {"status": "ok", "template_kind": template_kind, "path": path}


@router.post("/competitions/{competition_id}/special/import-participants")
async def import_special_participants(
    competition_id: UUID,
    file: UploadFile = File(...),
    register_to_competition: bool = Query(True, description="Register imported participants to this competition"),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Import participants for a special olympiad from JSON/CSV/XLSX."""
    competition_repo = CompetitionRepositoryImpl(db)
    competition = await competition_repo.get_by_id(competition_id)
    if not competition:
        raise HTTPException(status_code=404, detail="РћР»РёРјРїРёР°РґР° РЅРµ РЅР°Р№РґРµРЅР°")
    if not competition.is_special:
        raise HTTPException(status_code=400, detail="Р ВР СР С—Р С•РЎР‚РЎвЂљ Р Т‘Р С•РЎРѓРЎвЂљРЎС“Р С—Р ВµР Р… РЎвЂљР С•Р В»РЎРЉР С”Р С• Р Т‘Р В»РЎРЏ Р С•Р В»Р С‘Р СР С—Р С‘Р В°Р Т‘ РЎРѓ Р С—Р С•Р СР ВµРЎвЂљР С”Р С•Р в„– 'Р С•РЎРѓР С•Р В±Р В°РЎРЏ'")

    file_name = file.filename or ""
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Р¤Р°Р№Р» РїСѓСЃС‚РѕР№")

    try:
        rows = _parse_import_file(file_name, file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not rows:
        return {
            "total_rows": 0,
            "created_users": 0,
            "created_participants": 0,
            "registered_to_competition": 0,
            "skipped": 0,
            "errors": [],
        }

    from ....domain.entities import Institution, Participant

    user_repo = UserRepositoryImpl(db)
    participant_repo = ParticipantRepositoryImpl(db)
    institution_repo = InstitutionRepositoryImpl(db)
    registration_repo = RegistrationRepositoryImpl(db)
    entry_token_repo = EntryTokenRepositoryImpl(db)
    register_uc = RegisterForCompetitionUseCase(
        registration_repository=registration_repo,
        competition_repository=competition_repo,
        participant_repository=participant_repo,
        entry_token_repository=entry_token_repo,
        token_service=TokenService(settings.hmac_secret_key),
    )

    summary = {
        "total_rows": len(rows),
        "created_users": 0,
        "created_participants": 0,
        "registered_to_competition": 0,
        "skipped": 0,
        "errors": [],
    }

    for idx, row in enumerate(rows, start=1):
        try:
            normalized = _normalize_record(row)
            full_name = str(normalized.get("full_name") or "").strip()
            institution_name = str(normalized.get("institution") or "").strip()

            if len(full_name) < 2:
                raise ValueError("Р СџР С•Р В»Р Вµ Р В¤Р ВР С› Р С•Р В±РЎРЏР В·Р В°РЎвЂљР ВµР В»РЎРЉР Р…Р С•")
            if len(institution_name) < 2:
                raise ValueError("РџРѕР»Рµ Р’РЈР—/СѓС‡СЂРµР¶РґРµРЅРёРµ РѕР±СЏР·Р°С‚РµР»СЊРЅРѕ")

            email = str(normalized.get("email") or "").strip().lower()
            if not email:
                email = f"imported.{uuid4().hex[:16]}@participants.local"

            institution_location_raw = normalized.get("institution_location")
            institution_location = (
                str(institution_location_raw).strip()
                if institution_location_raw is not None and str(institution_location_raw).strip()
                else None
            )
            is_captain = _parse_bool(normalized.get("is_captain"))
            dob = _parse_dob(normalized.get("dob"))

            institution = await institution_repo.get_by_name(institution_name)
            if not institution:
                institution = await institution_repo.create(
                    Institution(
                        id=uuid4(),
                        name=institution_name,
                        city=institution_location,
                    )
                )

            user = await user_repo.get_by_email(email)
            participant = None

            if user is None:
                generated_password = secrets.token_urlsafe(12)
                user = await user_repo.create(
                    User(
                        id=uuid4(),
                        email=email,
                        password_hash=hash_password(generated_password),
                        role=UserRole.PARTICIPANT,
                        is_active=True,
                    )
                )
                summary["created_users"] += 1
            elif user.role != UserRole.PARTICIPANT:
                raise ValueError(f"Email {email} СѓР¶Рµ Р·Р°РЅСЏС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»РµРј СЃ СЂРѕР»СЊСЋ {user.role.value}")

            participant = await participant_repo.get_by_user_id(user.id)
            if participant is None:
                participant = await participant_repo.create(
                    Participant(
                        id=uuid4(),
                        user_id=user.id,
                        full_name=full_name,
                        school=institution_name,
                        grade=None,
                        institution_id=institution.id,
                        institution_location=institution_location,
                        is_captain=is_captain,
                        dob=dob,
                    )
                )
                summary["created_participants"] += 1
            else:
                participant.update_profile(
                    full_name=full_name,
                    school=institution_name,
                    institution_location=institution_location,
                    is_captain=is_captain,
                    dob=dob,
                )
                participant.institution_id = institution.id
                await participant_repo.update(participant)

            if register_to_competition:
                try:
                    await register_uc.execute(
                        participant_id=participant.id,
                        competition_id=competition_id,
                        skip_status_check=True,
                    )
                    summary["registered_to_competition"] += 1
                except ValueError as exc:
                    if "СѓР¶Рµ Р·Р°СЂРµРіРёСЃС‚СЂРёСЂРѕРІР°РЅС‹" in str(exc):
                        summary["skipped"] += 1
                    else:
                        raise

        except Exception as exc:  # noqa: BLE001
            summary["errors"].append({"row": idx, "error": str(exc)})

    return summary


@router.post("/competitions/{competition_id}/special/admit-all-and-download")
async def admit_all_special_and_download(
    competition_id: UUID,
    request: Request,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Admit all pending participants in special olympiad and return ZIP with sheets by participant folders."""
    competition_repo = CompetitionRepositoryImpl(db)
    competition = await competition_repo.get_by_id(competition_id)
    if not competition:
        raise HTTPException(status_code=404, detail="РћР»РёРјРїРёР°РґР° РЅРµ РЅР°Р№РґРµРЅР°")
    if not competition.is_special:
        raise HTTPException(status_code=400, detail="РћРїРµСЂР°С†РёСЏ РґРѕСЃС‚СѓРїРЅР° С‚РѕР»СЊРєРѕ РґР»СЏ РѕР»РёРјРїРёР°Рґ СЃ РїРѕРјРµС‚РєРѕР№ 'РѕСЃРѕР±Р°СЏ'")

    from ....infrastructure.database.models import (
        RegistrationModel,
        AnswerSheetModel,
    )

    registration_stmt = (
        select(RegistrationModel)
        .where(RegistrationModel.competition_id == competition_id)
        .options(
            selectinload(RegistrationModel.participant),
            selectinload(RegistrationModel.entry_token),
            selectinload(RegistrationModel.attempts),
        )
        .order_by(RegistrationModel.created_at.asc())
    )
    registrations_result = await db.execute(registration_stmt)
    registrations = registrations_result.scalars().all()

    approve_uc = ApproveAdmissionUseCase(
        token_service=TokenService(settings.hmac_secret_key),
        entry_token_repository=EntryTokenRepositoryImpl(db),
        registration_repository=RegistrationRepositoryImpl(db),
        competition_repository=competition_repo,
        attempt_repository=AttemptRepositoryImpl(db),
        audit_log_repository=AuditLogRepositoryImpl(db),
        answer_sheet_repository=AnswerSheetRepositoryImpl(db),
        storage=MinIOStorage(),
        sheet_generator=SheetGenerator(),
        room_repository=RoomRepositoryImpl(db),
        seat_assignment_repository=SeatAssignmentRepositoryImpl(db),
        participant_repository=ParticipantRepositoryImpl(db),
    )

    admitted_now = 0
    admit_errors: list[dict[str, Any]] = []

    # 1) Admit pending registrations.
    for reg in registrations:
        if reg.status.value != "pending":
            continue
        if not reg.entry_token or not reg.entry_token.raw_token:
            admit_errors.append(
                {
                    "registration_id": str(reg.id),
                    "participant": reg.participant.full_name if reg.participant else "вЂ”",
                    "error": "РЈ СЂРµРіРёСЃС‚СЂР°С†РёРё РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚ raw entry token",
                }
            )
            continue

        try:
            await approve_uc.execute(
                registration_id=reg.id,
                raw_entry_token=reg.entry_token.raw_token,
                admitter_user_id=current_user.id,
                ip_address=request.client.host if request.client else None,
            )
            admitted_now += 1
        except Exception as exc:  # noqa: BLE001
            admit_errors.append(
                {
                    "registration_id": str(reg.id),
                    "participant": reg.participant.full_name if reg.participant else "вЂ”",
                    "error": str(exc),
                }
            )

    # 2) Reload registrations to include created attempts.
    registrations_result = await db.execute(registration_stmt)
    registrations = registrations_result.scalars().all()

    # 3) Build ZIP archive (DOCX templates + legacy PDFs).
    storage = MinIOStorage()
    word_generator = WordTemplateGenerator()
    template_paths = word_generator.get_template_paths()
    tours = _extract_special_tours(competition)
    zip_buffer = io.BytesIO()
    added_files = 0
    mode_labels = {
        "individual": "Р ВР Р…Р Т‘Р С‘Р Р†Р С‘Р Т‘РЎС“Р В°Р В»РЎРЉР Р…РЎвЂ№Р в„–",
        "individual_captains": "Р ВР Р…Р Т‘Р С‘Р Р†Р С‘Р Т‘РЎС“Р В°Р В»РЎРЉР Р…РЎвЂ№Р в„– (Р С”Р В°Р С—Р С‘РЎвЂљР В°Р Р…РЎвЂ№)",
        "team": "РљРѕРјР°РЅРґРЅС‹Р№",
    }

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Include editable templates in archive for quick customization.
        try:
            zf.write(template_paths["answer_blank"], arcname="_templates/special_answer_blank_template.docx")
            zf.write(template_paths["a3_cover"], arcname="_templates/special_cover_a3_template.docx")
            added_files += 2
        except Exception:  # noqa: BLE001
            pass

        for reg in registrations:
            participant = reg.participant
            if not participant:
                continue
            if not reg.attempts:
                continue

            attempt = reg.attempts[0]
            folder = _slugify_folder_name(f"{participant.full_name}_{participant.id}")

            sheets_stmt = (
                select(AnswerSheetModel)
                .where(AnswerSheetModel.attempt_id == attempt.id)
                .order_by(AnswerSheetModel.created_at.asc())
            )
            sheets_result = await db.execute(sheets_stmt)
            sheets = sheets_result.scalars().all()

            # Generate DOCX set based on editable Word templates.
            for tour in tours:
                tour_number = int(tour["tour_number"])
                mode = str(tour["mode"])
                mode_label = mode_labels.get(mode, mode)
                task_numbers = tour["task_numbers"]

                cover_qr_payload = f"attempt:{attempt.id}:tour:{tour_number}:cover"
                try:
                    cover_docx = word_generator.generate_a3_cover(
                        qr_payload=cover_qr_payload,
                        tour_number=tour_number,
                        mode=mode_label,
                    )
                    zf.writestr(f"{folder}/A3_tour_{tour_number}.docx", cover_docx)
                    added_files += 1
                except Exception as exc:  # noqa: BLE001
                    admit_errors.append(
                        {
                            "registration_id": str(reg.id),
                            "participant": participant.full_name,
                            "error": f"A3 tour {tour_number}: {exc}",
                        }
                    )

                for task_number in task_numbers:
                    task_qr_payload = f"attempt:{attempt.id}:tour:{tour_number}:task:{task_number}"
                    try:
                        task_docx = word_generator.generate_answer_blank(
                            qr_payload=task_qr_payload,
                            tour_number=tour_number,
                            task_number=int(task_number),
                            mode=mode_label,
                        )
                        zf.writestr(
                            f"{folder}/tour_{tour_number}/task_{task_number}.docx",
                            task_docx,
                        )
                        added_files += 1
                    except Exception as exc:  # noqa: BLE001
                        admit_errors.append(
                            {
                                "registration_id": str(reg.id),
                                "participant": participant.full_name,
                                "error": f"Task {tour_number}/{task_number}: {exc}",
                            }
                        )

            # Keep existing generated PDFs for backward compatibility with scan flow.
            if not sheets and attempt.pdf_file_path:
                try:
                    pdf_bytes = storage.download_file(
                        bucket=settings.minio_bucket_sheets,
                        object_name=attempt.pdf_file_path,
                    )
                    zf.writestr(f"{folder}/legacy/primary.pdf", pdf_bytes)
                    added_files += 1
                except Exception:  # noqa: BLE001
                    pass
                continue

            for index, sheet in enumerate(sheets, start=1):
                if not sheet.pdf_file_path:
                    continue
                try:
                    pdf_bytes = storage.download_file(
                        bucket=settings.minio_bucket_sheets,
                        object_name=sheet.pdf_file_path,
                    )
                    zf.writestr(f"{folder}/legacy/{index}_{sheet.kind.value}.pdf", pdf_bytes)
                    added_files += 1
                except Exception:  # noqa: BLE001
                    continue

    zip_buffer.seek(0)

    headers = {
        "Content-Disposition": f'attachment; filename="special_olympiad_{competition_id}.zip"',
        "X-Admitted-Now": str(admitted_now),
        "X-Archive-Files": str(added_files),
        "X-Admit-Errors": json.dumps(admit_errors),
    }
    return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)

