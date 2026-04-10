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
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from ....infrastructure.database import get_db
from ....infrastructure.database.models import BadgeTemplateModel
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
from ....domain.entities import SeatAssignment, User
from ....domain.value_objects import RegistrationStatus, UserRole
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
        "фио",
        "name",
        "participant_name",
        "participant",
    },
    "email": {"email", "почта", "e-mail", "mail"},
    "institution": {
        "institution",
        "institution_name",
        "school",
        "university",
        "вуз",
        "учреждение",
        "учебное учреждение",
    },
    "institution_location": {
        "institution_location",
        "location",
        "city",
        "campus",
        "местоположение",
        "город",
        "местоположение вуза",
        "город вуза",
    },
    "is_captain": {"is_captain", "captain", "капитан", "капитан/не капитан"},
    "dob": {"dob", "birth_date", "date_of_birth", "дата рождения", "рождение"},
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
    return normalized in {"1", "true", "yes", "y", "да", "капитан"}


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
    raise ValueError(f"Не удалось распознать дату рождения: {value}")


def _slugify_folder_name(value: str) -> str:
    safe = re.sub(r"[^\w\-. ]+", "_", value, flags=re.UNICODE).strip()
    safe = re.sub(r"\s+", "_", safe)
    return safe[:80] or "participant"


def _split_full_name(full_name: str) -> tuple[str, str, str]:
    parts = [part for part in re.split(r"\s+", (full_name or "").strip()) if part]
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", ""
    if len(parts) == 2:
        return parts[0], parts[1], ""
    return parts[0], parts[1], " ".join(parts[2:])


def _build_badge_photo_lookup_keys(
    city: str | None,
    institution_name: str | None,
    last_name: str,
    first_name: str,
    middle_name: str,
) -> list[str]:
    fio = "_".join(part for part in [last_name, first_name, middle_name] if part).strip("_")
    if not fio:
        return []
    normalize = WordTemplateGenerator._normalize_photo_key  # type: ignore[attr-defined]
    return [
        normalize(f"{city or ''}/{institution_name or ''}/{fio}"),
        normalize(f"{institution_name or ''}/{fio}"),
        normalize(fio),
    ]


async def _load_badge_photo_index(db: AsyncSession) -> dict[str, bytes]:
    from ....infrastructure.database.models import BadgePhotoModel

    result = await db.execute(select(BadgePhotoModel.normalized_key, BadgePhotoModel.image_bytes))
    index: dict[str, bytes] = {}
    for row in result.all():
        key = (row.normalized_key or "").strip().lower()
        if not key:
            continue
        index[key] = row.image_bytes
        # Add partial-path aliases (last 1-3 segments) so that a ZIP with a root
        # folder (e.g. "photos_archive/city/inst/name") still matches lookups that
        # omit the root prefix ("city/inst/name", "inst/name", "name").
        parts = [p for p in key.split("/") if p]
        for n in range(1, min(4, len(parts))):
            alias = "/".join(parts[-n:])
            index.setdefault(alias, row.image_bytes)
    return index


def _find_badge_photo_bytes(
    photo_index: dict[str, bytes],
    city: str | None,
    institution_name: str | None,
    last_name: str,
    first_name: str,
    middle_name: str,
) -> bytes | None:
    keys = _build_badge_photo_lookup_keys(
        city=city,
        institution_name=institution_name,
        last_name=last_name,
        first_name=first_name,
        middle_name=middle_name,
    )
    for key in keys:
        if key in photo_index:
            return photo_index[key]
    return None


def _parse_import_file(file_name: str, file_bytes: bytes) -> list[dict[str, Any]]:
    lower_name = file_name.lower()

    if lower_name.endswith(".json"):
        payload = json.loads(file_bytes.decode("utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("participants", [])
        if not isinstance(payload, list):
            raise ValueError("JSON должен быть массивом участников или объектом с ключом participants")
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
            raise ValueError("Не удалось декодировать CSV. Используйте UTF-8 или CP1251")

        reader = csv.DictReader(io.StringIO(text))
        return [_normalize_record(row) for row in reader]

    if lower_name.endswith(".xlsx"):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise ValueError("Для импорта XLSX требуется зависимость openpyxl") from exc

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

    raise ValueError("Поддерживаются только файлы .json, .csv, .xlsx")


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
            raise HTTPException(status_code=400, detail="Указан несуществующий номер тура")

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


async def _ensure_seat_assignments_for_competition(competition, db: AsyncSession) -> int:
    """Auto-assign seats for active registrations missing seat assignment.

    Used by seating-plan view to keep schema non-empty without heavy per-registration queries.
    Rule for `individual` / `individual_captains`: participants from the same
    institution are not placed in adjacent seats (left/right/front/back/diagonal)
    when there is any valid non-conflicting seat.
    """
    from ....infrastructure.database.models import (
        ParticipantModel,
        RegistrationModel,
        RoomModel,
        SeatAssignmentModel,
    )

    rooms_result = await db.execute(
        select(RoomModel)
        .where(RoomModel.competition_id == competition.id)
        .order_by(RoomModel.name.asc())
    )
    rooms = rooms_result.scalars().all()
    if not rooms:
        return 0

    room_ids = [room.id for room in rooms]
    rooms_by_id = {room.id: room for room in rooms}

    existing_result = await db.execute(
        select(
            SeatAssignmentModel.room_id,
            SeatAssignmentModel.seat_number,
            ParticipantModel.institution_id,
        )
        .join(RegistrationModel, RegistrationModel.id == SeatAssignmentModel.registration_id)
        .join(ParticipantModel, ParticipantModel.id == RegistrationModel.participant_id)
        .where(SeatAssignmentModel.room_id.in_(room_ids))
    )
    taken_by_room: dict[UUID, set[int]] = {room.id: set() for room in rooms}
    institution_seats_by_room: dict[UUID, dict[UUID, list[int]]] = {room.id: {} for room in rooms}
    for row in existing_result:
        taken_by_room[row.room_id].add(int(row.seat_number))
        if row.institution_id:
            room_map = institution_seats_by_room[row.room_id]
            room_map.setdefault(row.institution_id, []).append(int(row.seat_number))

    missing_result = await db.execute(
        select(
            RegistrationModel.id.label("registration_id"),
            ParticipantModel.institution_id.label("institution_id"),
            ParticipantModel.is_captain.label("is_captain"),
        )
        .join(ParticipantModel, ParticipantModel.id == RegistrationModel.participant_id)
        .outerjoin(SeatAssignmentModel, SeatAssignmentModel.registration_id == RegistrationModel.id)
        .where(RegistrationModel.competition_id == competition.id)
        .where(RegistrationModel.status != RegistrationStatus.CANCELLED)
        .where(SeatAssignmentModel.id.is_(None))
        .order_by(RegistrationModel.created_at.asc())
    )
    missing_rows = missing_result.all()
    if not missing_rows:
        return 0

    special_context = _resolve_special_tour_context(competition, tour_number=None)
    tour_mode = str(special_context.get("mode")) if special_context else ""
    is_captains_mode = tour_mode == "individual_captains"
    apply_institution_distance_rule = tour_mode in {"individual", "individual_captains"}
    is_team_mode = bool(special_context and special_context.get("is_team_mode"))
    settings_payload = competition.special_settings or {}
    captains_room_id: UUID | None = None
    raw_captains_room_id = settings_payload.get("captains_room_id")
    if is_captains_mode and raw_captains_room_id:
        try:
            parsed = UUID(str(raw_captains_room_id))
            if parsed in rooms_by_id:
                captains_room_id = parsed
        except (TypeError, ValueError):
            captains_room_id = None

    room_priority_all = [room.id for room in rooms]
    room_columns = {
        room.id: _resolve_room_seat_matrix_columns(
            competition=competition,
            room_id=room.id,
            is_team_mode=is_team_mode,
        )
        for room in rooms
    }
    room_seats_per_table = {
        room.id: _resolve_room_seats_per_table(
            competition=competition,
            room_id=room.id,
            is_team_mode=is_team_mode,
        )
        for room in rooms
    }

    def seat_grid_position(room_id: UUID, seat_number: int) -> tuple[int, int]:
        cols = max(int(room_columns.get(room_id, 3)), 1)
        row = (seat_number - 1) // cols
        col = (seat_number - 1) % cols
        return row, col

    def same_institution_neighborhood_conflicts(room_id: UUID, seat_number: int, institution_id: UUID | None) -> int:
        if not institution_id:
            return 0
        target_row, target_col = seat_grid_position(room_id, seat_number)
        conflicts = 0
        for occupied_seat in institution_seats_by_room[room_id].get(institution_id, []):
            occ_row, occ_col = seat_grid_position(room_id, occupied_seat)
            if abs(occ_row - target_row) <= 1 and abs(occ_col - target_col) <= 1:
                conflicts += 1
        return conflicts

    def same_institution_table_conflicts(room_id: UUID, seat_number: int, institution_id: UUID | None) -> int:
        if not institution_id:
            return 0
        seats_per_table = max(int(room_seats_per_table.get(room_id, 1)), 1)
        target_table = (seat_number - 1) // seats_per_table
        conflicts = 0
        for occupied_seat in institution_seats_by_room[room_id].get(institution_id, []):
            occupied_table = (occupied_seat - 1) // seats_per_table
            if occupied_table == target_table:
                conflicts += 1
        return conflicts

    def candidate_room_order(is_captain: bool) -> list[UUID]:
        if not is_captains_mode or captains_room_id is None:
            return room_priority_all
        if is_captain:
            return [captains_room_id] + [rid for rid in room_priority_all if rid != captains_room_id]
        return [rid for rid in room_priority_all if rid != captains_room_id] + [captains_room_id]

    seat_repo = SeatAssignmentRepositoryImpl(db)
    variants_count = max(int(getattr(competition, "variants_count", 1) or 1), 1)
    assigned_count = 0

    for missing in missing_rows:
        best_strict: tuple[tuple[int, int, int, int], UUID, int] | None = None
        best_relaxed: tuple[tuple[int, int, int, int], UUID, int] | None = None

        for room_priority_index, room_id in enumerate(candidate_room_order(bool(missing.is_captain))):
            room = rooms_by_id[room_id]
            taken = taken_by_room[room_id]
            for seat_number in range(1, room.capacity + 1):
                if seat_number in taken:
                    continue

                neighborhood_conflicts = (
                    same_institution_neighborhood_conflicts(room_id, seat_number, missing.institution_id)
                    if apply_institution_distance_rule
                    else 0
                )
                table_conflicts = (
                    same_institution_table_conflicts(room_id, seat_number, missing.institution_id)
                    if apply_institution_distance_rule
                    else 0
                )
                same_inst_in_room = (
                    len(institution_seats_by_room[room_id].get(missing.institution_id, []))
                    if missing.institution_id
                    else 0
                )

                score = (same_inst_in_room, room_priority_index, len(taken), seat_number)
                if neighborhood_conflicts == 0 and table_conflicts == 0:
                    candidate = (score, room_id, seat_number)
                    if best_strict is None or candidate[0] < best_strict[0]:
                        best_strict = candidate
                else:
                    relaxed_score = (
                        neighborhood_conflicts + table_conflicts,
                        same_inst_in_room,
                        room_priority_index,
                        seat_number,
                    )
                    candidate = (relaxed_score, room_id, seat_number)
                    if best_relaxed is None or candidate[0] < best_relaxed[0]:
                        best_relaxed = candidate

        selected = best_strict or best_relaxed
        if selected is None:
            continue
        _, chosen_room_id, chosen_seat_number = selected

        variant_number = (chosen_seat_number % variants_count) + 1
        await seat_repo.create(
            SeatAssignment(
                registration_id=missing.registration_id,
                room_id=chosen_room_id,
                seat_number=chosen_seat_number,
                variant_number=variant_number,
            )
        )
        taken_by_room[chosen_room_id].add(chosen_seat_number)
        if missing.institution_id:
            institution_seats_by_room[chosen_room_id].setdefault(missing.institution_id, []).append(chosen_seat_number)
        assigned_count += 1

    return assigned_count


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
        raise HTTPException(status_code=400, detail="Email уже используется")

    # Validate participant-specific fields
    if body.role == UserRole.PARTICIPANT:
        if not body.full_name or len(body.full_name.strip()) < 2:
            raise HTTPException(status_code=400, detail="ФИО обязательно для участников (минимум 2 символа)")
        if not body.school or len(body.school.strip()) < 2:
            raise HTTPException(status_code=400, detail="Учебное учреждение обязательно для участников (минимум 2 символа)")

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
        raise HTTPException(status_code=404, detail="Пользователь не найден")

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
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя деактивировать себя")

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
                participant_name=participant.full_name if participant else "—",
                participant_school=participant.school if participant else "—",
                participant_institution_location=participant.institution_location if participant else None,
                participant_is_captain=participant.is_captain if participant else False,
                institution_name=institution_name,
                entry_token=entry_token_raw,
                status=reg.status.value,
            )
        )

    return AdminRegistrationListResponse(items=items, total=len(items))


@router.post("/registrations/{competition_id}/badges-pdf/start")
async def start_badges_pdf(
    competition_id: UUID,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Start asynchronous badge PDF generation. Returns a task_id to poll for status."""
    from ....infrastructure.database.models import CompetitionModel
    from ....infrastructure.tasks.badge_tasks import generate_badges_pdf

    comp_result = await db.execute(
        select(CompetitionModel).where(CompetitionModel.id == competition_id)
    )
    if not comp_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Олимпиада не найдена")

    task = generate_badges_pdf.delay(str(competition_id))
    return {"task_id": task.id}


@router.get("/badge-tasks/{task_id}/status")
async def get_badge_task_status(
    task_id: str,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Poll the status of a badge PDF generation task."""
    from ....infrastructure.tasks.celery_app import celery_app as _celery

    result = _celery.AsyncResult(task_id)
    state = result.state  # PENDING, STARTED, PROGRESS, SUCCESS, FAILURE
    info = result.info or {}

    if state == "SUCCESS":
        payload = info if isinstance(info, dict) else {}
        return {
            "state": "SUCCESS",
            "status": payload.get("status", "completed"),
            "count": payload.get("count"),
            "object_name": payload.get("object_name"),
        }
    if state == "FAILURE":
        return {"state": "FAILURE", "message": str(info)}
    if state == "PROGRESS" and isinstance(info, dict):
        return {
            "state": "PROGRESS",
            "stage": info.get("stage", ""),
            "current": info.get("current", 0),
            "total": info.get("total", 0),
        }
    return {"state": state}


@router.get("/badge-tasks/{task_id}/download")
async def download_badge_task_pdf(
    task_id: str,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Download the generated badge PDF once the task is complete."""
    from ....infrastructure.tasks.celery_app import celery_app as _celery
    from ....infrastructure.storage import MinIOStorage
    from ....infrastructure.tasks.badge_tasks import BADGE_PDF_BUCKET

    result = _celery.AsyncResult(task_id)
    if result.state != "SUCCESS":
        raise HTTPException(status_code=400, detail=f"Задача ещё не завершена (состояние: {result.state})")

    payload = result.result or {}
    if not isinstance(payload, dict) or payload.get("status") != "completed":
        message = payload.get("message", "неизвестная ошибка") if isinstance(payload, dict) else str(payload)
        raise HTTPException(status_code=500, detail=f"Генерация завершилась с ошибкой: {message}")

    object_name = payload.get("object_name")
    if not object_name:
        raise HTTPException(status_code=500, detail="Результат задачи не содержит пути к файлу")

    try:
        storage = MinIOStorage()
        pdf_bytes = storage.download_file(bucket=BADGE_PDF_BUCKET, object_name=object_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Не удалось загрузить PDF из хранилища: {exc}") from exc

    filename = object_name.rsplit("/", 1)[-1]
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/registrations/{competition_id}/badges-pdf")
async def download_badges_pdf(
    competition_id: UUID,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Download template-based badge PDF grouped by institution."""
    from ....infrastructure.database.models import (
        RegistrationModel,
        CompetitionModel,
        ParticipantModel,
    )
    from ....infrastructure.pdf.badge_template_pdf_generator import (
        BadgeTemplatePdfGenerator,
        TemplateBadgePdfItem,
    )
    from io import BytesIO

    comp_result = await db.execute(
        select(CompetitionModel).where(CompetitionModel.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    if not competition:
        raise HTTPException(status_code=404, detail="Олимпиада не найдена")

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

    word_generator = WordTemplateGenerator()
    if not word_generator.is_docx_to_pdf_available():
        raise HTTPException(
            status_code=500,
            detail="Для генерации PDF бейджей из DOCX-шаблона требуется LibreOffice (soffice).",
        )
    photo_index = await _load_badge_photo_index(db)

    prepared: list[dict[str, Any]] = []
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
            institution_name = participant.institution.name or ""

        last_name, first_name, middle_name = _split_full_name(participant.full_name)
        photo_bytes = _find_badge_photo_bytes(
            photo_index=photo_index,
            city=participant.institution_location,
            institution_name=institution_name,
            last_name=last_name,
            first_name=first_name,
            middle_name=middle_name,
        )

        prepared.append(
            {
                "institution": institution_name,
                "full_name": participant.full_name,
                "docx": word_generator.generate_badge_docx(
                    qr_payload=entry_token_raw,
                    first_name=first_name,
                    last_name=last_name,
                    middle_name=middle_name,
                    role="УЧАСТНИК",
                    participant_school=participant.school,
                    institution_name=institution_name,
                    competition_name=competition.name,
                    photo_bytes=photo_bytes,
                ),
            }
        )

    prepared.sort(key=lambda item: (item["institution"] or "", item["full_name"] or ""))
    if not prepared:
        raise HTTPException(status_code=400, detail="Нет зарегистрированных участников для генерации бейджей")

    docx_files: dict[str, bytes] = {}
    name_to_institution: dict[str, str] = {}
    for index, item in enumerate(prepared, start=1):
        file_name = f"badge_{index:04d}.docx"
        docx_files[file_name] = item["docx"]
        name_to_institution[file_name] = item["institution"]

    try:
        converted_pdf = word_generator.convert_docx_files_to_pdf(docx_files)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Не удалось конвертировать бейджи в PDF: {exc}") from exc
    template_items: list[TemplateBadgePdfItem] = []
    for file_name in docx_files:
        template_items.append(
            TemplateBadgePdfItem(
                institution=name_to_institution[file_name],
                pdf_bytes=converted_pdf[file_name],
            )
        )

    generator = BadgeTemplatePdfGenerator()
    pdf_bytes = generator.generate_grouped_pdf(competition.name, template_items)

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="badges_{competition_id}.pdf"'
        },
    )

@router.get("/registrations/{competition_id}/badges-docx")
async def download_badges_docx(
    competition_id: UUID,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Download badge DOCX files generated from editable Word template."""
    from ....infrastructure.database.models import (
        RegistrationModel,
        CompetitionModel,
        ParticipantModel,
    )
    from io import BytesIO

    comp_result = await db.execute(
        select(CompetitionModel).where(CompetitionModel.id == competition_id)
    )
    competition = comp_result.scalar_one_or_none()
    if not competition:
        raise HTTPException(status_code=404, detail="Олимпиада не найдена")

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

    word_generator = WordTemplateGenerator()
    template_paths = word_generator.get_template_paths()
    photo_index = await _load_badge_photo_index(db)
    zip_buffer = io.BytesIO()
    index = 1

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        try:
            zf.write(template_paths["badge"], arcname="_templates/badge_template.docx")
        except Exception:  # noqa: BLE001
            pass

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
                institution_name = participant.institution.name or ""

            last_name, first_name, middle_name = _split_full_name(participant.full_name)
            photo_bytes = _find_badge_photo_bytes(
                photo_index=photo_index,
                city=participant.institution_location,
                institution_name=institution_name,
                last_name=last_name,
                first_name=first_name,
                middle_name=middle_name,
            )
            badge_docx = word_generator.generate_badge_docx(
                qr_payload=entry_token_raw,
                first_name=first_name,
                last_name=last_name,
                middle_name=middle_name,
                role="УЧАСТНИК",
                participant_school=participant.school,
                institution_name=institution_name,
                competition_name=competition.name,
                photo_bytes=photo_bytes,
            )

            institution_slug = _slugify_folder_name(institution_name or "without_institution")
            participant_slug = _slugify_folder_name(participant.full_name)
            if not participant_slug:
                participant_slug = str(participant.id)
            filename = f"{institution_slug}/{index:03d}_{participant_slug}.docx"
            zf.writestr(filename, badge_docx)
            index += 1

    zip_buffer.seek(0)
    return StreamingResponse(
        BytesIO(zip_buffer.getvalue()),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="badges_{competition_id}_docx.zip"'
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
        raise HTTPException(status_code=404, detail="Олимпиада не найдена")

    await _ensure_seat_assignments_for_competition(competition=competition, db=db)

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
            {"kind": "badge", "path": paths["badge"]},
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
        raise HTTPException(status_code=404, detail="Неизвестный тип шаблона")

    path = paths[template_kind]
    try:
        with open(path, "rb") as f:
            content = f.read()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Не удалось открыть шаблон: {exc}")

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
        raise HTTPException(status_code=404, detail="Неизвестный тип шаблона")
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Нужен файл .docx")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой")

    path = paths[template_kind]
    try:
        with open(path, "wb") as f:
            f.write(content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Не удалось сохранить шаблон: {exc}")

    return {"status": "ok", "template_kind": template_kind, "path": path}


@router.post("/special/templates/badge/photos/upload")
async def upload_badge_photos_zip(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Upload ZIP archive with participant photos for badge template token {{PHOTO}}."""
    from ....infrastructure.database.models import BadgePhotoModel

    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Нужен ZIP-архив с фотографиями")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой")

    content_type_by_ext = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    records: dict[str, tuple[str, bytes, str]] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                ext = Path(info.filename).suffix.lower()
                if ext not in content_type_by_ext:
                    continue

                raw_path = str(info.filename).replace("\\", "/")
                raw_parts = [part for part in raw_path.split("/") if part]
                if not raw_parts or any(part == ".." for part in raw_parts):
                    continue

                normalized_key = WordTemplateGenerator._normalize_photo_key(  # type: ignore[attr-defined]
                    str(Path(raw_path).with_suffix("")).replace("\\", "/")
                )
                if not normalized_key:
                    continue

                image_bytes = zf.read(info)
                if not image_bytes:
                    continue

                records[normalized_key] = (
                    raw_path,
                    image_bytes,
                    content_type_by_ext[ext],
                )
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Некорректный ZIP-архив")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Не удалось обработать архив фотографий: {exc}")

    await db.execute(delete(BadgePhotoModel))
    for normalized_key, (original_path, image_bytes, content_type) in records.items():
        db.add(
            BadgePhotoModel(
                normalized_key=normalized_key,
                original_path=original_path,
                content_type=content_type,
                image_bytes=image_bytes,
            )
        )
    imported = len(records)

    return {
        "status": "ok",
        "imported_files": imported,
        "imported": imported,
        "path_hint": "Город/Учреждение/Фамилия_Имя_Отчество.png",
    }


@router.post("/special/templates/badge/fonts/upload")
async def upload_badge_fonts(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Upload TTF/OTF font files (single file or ZIP) used during LibreOffice badge PDF conversion.

    Fonts are stored on disk in the templates/word/fonts/ directory and are automatically
    passed to LibreOffice when generating badge PDFs, so custom fonts like Magistral are
    rendered correctly without requiring system-wide installation in the container.
    """
    word_generator = WordTemplateGenerator()
    word_generator.ensure_templates_exist()
    fonts_dir = word_generator.fonts_dir

    filename = (file.filename or "").lower()
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой")

    imported = 0

    if filename.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    ext = Path(info.filename).suffix.lower()
                    if ext not in {".ttf", ".otf"}:
                        continue
                    font_name = Path(info.filename).name
                    if not font_name:
                        continue
                    (fonts_dir / font_name).write_bytes(zf.read(info))
                    imported += 1
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Некорректный ZIP-архив")
    elif filename.endswith(".ttf") or filename.endswith(".otf"):
        font_name = Path(file.filename or "font").name
        (fonts_dir / font_name).write_bytes(content)
        imported = 1
    else:
        raise HTTPException(
            status_code=400,
            detail="Поддерживаются файлы .ttf, .otf или ZIP-архив с ними",
        )

    # Install fonts system-wide immediately so LibreOffice can use them
    # on the very next badge PDF generation without requiring a restart.
    word_generator.install_fonts_system_wide()

    return {"status": "ok", "imported_files": imported}


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
        raise HTTPException(status_code=404, detail="Олимпиада не найдена")
    if not competition.is_special:
        raise HTTPException(status_code=400, detail="Импорт доступен только для олимпиад с пометкой 'особая'")

    file_name = file.filename or ""
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Файл пустой")

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
                raise ValueError("Поле ФИО обязательно")
            if len(institution_name) < 2:
                raise ValueError("Поле ВУЗ/учреждение обязательно")

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
                raise ValueError(f"Email {email} уже занят пользователем с ролью {user.role.value}")

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
                    if "уже зарегистрированы" in str(exc):
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
        raise HTTPException(status_code=404, detail="Олимпиада не найдена")
    if not competition.is_special:
        raise HTTPException(status_code=400, detail="Операция доступна только для олимпиад с пометкой 'особая'")

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
                    "participant": reg.participant.full_name if reg.participant else "—",
                    "error": "У регистрации отсутствует raw entry token",
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
                    "participant": reg.participant.full_name if reg.participant else "—",
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
        "individual": "Индивидуальный",
        "individual_captains": "Индивидуальный (капитаны)",
        "team": "Командный",
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
                    zf.writestr(f"{folder}/tour_{tour_number}/A3_tour_{tour_number}.docx", cover_docx)
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
                        task_folder = f"{folder}/tour_{tour_number}/task_{task_number}"
                        zf.writestr(
                            f"{task_folder}/task_{task_number}.docx",
                            task_docx,
                        )
                        added_files += 1
                        for extra_i in range(1, 6):
                            extra_docx = word_generator.generate_answer_blank(
                                qr_payload=task_qr_payload,
                                tour_number=tour_number,
                                task_number=int(task_number),
                                mode=mode_label,
                                tour_task=f"{tour_number}/{task_number}/{extra_i}",
                            )
                            zf.writestr(
                                f"{task_folder}/дополнительные бланки/extra_{extra_i}.docx",
                                extra_docx,
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


# ══════════════════════════════════════════════════════════════════════════════
# Badge Template endpoints (JSON-based visual editor)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/competitions/{competition_id}/badge-template")
async def get_badge_template(
    competition_id: UUID,
    current_user: Annotated[Any, Depends(require_role(UserRole.ADMIN))],
    db: AsyncSession = Depends(get_db),
):
    """Return badge template config for a competition (no background bytes)."""
    result = await db.execute(
        select(BadgeTemplateModel).where(
            BadgeTemplateModel.competition_id == competition_id
        )
    )
    tmpl = result.scalar_one_or_none()
    if tmpl is None:
        return {
            "id": None,
            "competition_id": str(competition_id),
            "config_json": {
                "width_mm": 90,
                "height_mm": 120,
                "background_w_mm": 90,
                "background_h_mm": 120,
                "elements": [],
            },
            "print_per_page": 4,
            "has_background": False,
            "created_at": None,
            "updated_at": None,
        }
    return {
        "id": str(tmpl.id),
        "competition_id": str(tmpl.competition_id),
        "config_json": tmpl.config_json,
        "print_per_page": tmpl.print_per_page,
        "has_background": tmpl.background_image_bytes is not None,
        "created_at": tmpl.created_at.isoformat() if tmpl.created_at else None,
        "updated_at": tmpl.updated_at.isoformat() if tmpl.updated_at else None,
    }


@router.post("/competitions/{competition_id}/badge-template", status_code=200)
async def upsert_badge_template(
    competition_id: UUID,
    body: dict,
    current_user: Annotated[Any, Depends(require_role(UserRole.ADMIN))],
    db: AsyncSession = Depends(get_db),
):
    """Create or update badge template config for a competition.

    Body: {config_json: {...}, print_per_page: 4|6}
    """
    config_json = body.get("config_json", {})
    print_per_page = int(body.get("print_per_page", 4))
    if print_per_page not in (4, 6):
        print_per_page = 4

    result = await db.execute(
        select(BadgeTemplateModel).where(
            BadgeTemplateModel.competition_id == competition_id
        )
    )
    tmpl = result.scalar_one_or_none()

    if tmpl is None:
        import uuid as _uuid
        tmpl = BadgeTemplateModel(
            id=_uuid.uuid4(),
            competition_id=competition_id,
            config_json=config_json,
            print_per_page=print_per_page,
        )
        db.add(tmpl)
    else:
        tmpl.config_json = config_json
        tmpl.print_per_page = print_per_page
        tmpl.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(tmpl)
    return {
        "id": str(tmpl.id),
        "competition_id": str(tmpl.competition_id),
        "config_json": tmpl.config_json,
        "print_per_page": tmpl.print_per_page,
        "has_background": tmpl.background_image_bytes is not None,
        "created_at": tmpl.created_at.isoformat() if tmpl.created_at else None,
        "updated_at": tmpl.updated_at.isoformat() if tmpl.updated_at else None,
    }


@router.post("/competitions/{competition_id}/badge-template/background", status_code=200)
async def upload_badge_template_background(
    competition_id: UUID,
    current_user: Annotated[Any, Depends(require_role(UserRole.ADMIN))],
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
):
    """Upload a background image for the badge template."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Файл должен быть изображением")

    img_bytes = await file.read()

    result = await db.execute(
        select(BadgeTemplateModel).where(
            BadgeTemplateModel.competition_id == competition_id
        )
    )
    tmpl = result.scalar_one_or_none()

    if tmpl is None:
        import uuid as _uuid
        tmpl = BadgeTemplateModel(
            id=_uuid.uuid4(),
            competition_id=competition_id,
            config_json={
                "width_mm": 90,
                "height_mm": 120,
                "background_w_mm": 90,
                "background_h_mm": 120,
                "elements": [],
            },
            print_per_page=4,
            background_image_bytes=img_bytes,
        )
        db.add(tmpl)
    else:
        tmpl.background_image_bytes = img_bytes
        tmpl.updated_at = datetime.utcnow()

    await db.commit()
    return {"status": "ok", "size": len(img_bytes)}


@router.get("/competitions/{competition_id}/badge-template/background")
async def get_badge_template_background(
    competition_id: UUID,
    current_user: Annotated[Any, Depends(require_role(UserRole.ADMIN))],
    db: AsyncSession = Depends(get_db),
):
    """Stream the background image bytes."""
    result = await db.execute(
        select(BadgeTemplateModel).where(
            BadgeTemplateModel.competition_id == competition_id
        )
    )
    tmpl = result.scalar_one_or_none()
    if tmpl is None or not tmpl.background_image_bytes:
        raise HTTPException(status_code=404, detail="Фоновое изображение не найдено")

    return StreamingResponse(
        io.BytesIO(tmpl.background_image_bytes),
        media_type="image/png",
        headers={"Cache-Control": "no-cache"},
    )


@router.delete("/competitions/{competition_id}/badge-template", status_code=200)
async def delete_badge_template(
    competition_id: UUID,
    current_user: Annotated[Any, Depends(require_role(UserRole.ADMIN))],
    db: AsyncSession = Depends(get_db),
):
    """Delete the badge template for a competition."""
    result = await db.execute(
        select(BadgeTemplateModel).where(
            BadgeTemplateModel.competition_id == competition_id
        )
    )
    tmpl = result.scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    await db.delete(tmpl)
    await db.commit()
    return {"status": "deleted"}


# ── Font serving for badge editor preview ─────────────────────────────────────

_FONTS_DIR = Path(__file__).resolve().parents[5] / "templates" / "word" / "fonts"


@router.get("/badge-fonts")
async def list_badge_fonts(
    current_user: Annotated[Any, Depends(require_role(UserRole.ADMIN))],
):
    """List available custom font filenames for badge editor."""
    if not _FONTS_DIR.exists():
        return []
    return [
        f.name
        for f in sorted(_FONTS_DIR.iterdir())
        if f.suffix.lower() in (".ttf", ".otf")
    ]


@router.get("/badge-fonts/{filename}")
async def get_badge_font(
    filename: str,
    current_user: Annotated[Any, Depends(require_role(UserRole.ADMIN))],
):
    """Serve a custom font file for the badge editor preview."""
    import re as _re
    if not _re.match(r'^[\w\- ]+\.(ttf|otf)$', filename, _re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Недопустимое имя файла")
    font_path = _FONTS_DIR / filename
    if not font_path.exists() or font_path.parent.resolve() != _FONTS_DIR.resolve():
        raise HTTPException(status_code=404, detail="Шрифт не найден")
    suffix = font_path.suffix.lower()
    media_type = "font/otf" if suffix == ".otf" else "font/ttf"
    return StreamingResponse(
        io.BytesIO(font_path.read_bytes()),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
