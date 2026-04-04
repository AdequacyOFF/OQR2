"""Competition entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from uuid import UUID, uuid4

from ..value_objects import CompetitionStatus


@dataclass
class Competition:
    """Competition entity.

    Attributes:
        id: Unique identifier
        name: Competition name
        date: Competition date
        registration_start: When registration opens
        registration_end: When registration closes
        variants_count: Number of test variants
        max_score: Maximum possible score
        status: Competition status
        created_by: User who created the competition
        created_at: When competition was created
        updated_at: When competition was last updated
    """
    name: str
    date: date
    registration_start: datetime
    registration_end: datetime
    variants_count: int
    max_score: int
    created_by: UUID
    id: UUID = field(default_factory=uuid4)
    is_special: bool = False
    special_tours_count: int | None = None
    special_tour_modes: list[str] | None = None
    special_settings: dict | None = None
    status: CompetitionStatus = CompetitionStatus.DRAFT
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if not self.name or len(self.name.strip()) < 3:
            raise ValueError("Название олимпиады должно быть не менее 3 символов")
        if self.registration_start >= self.registration_end:
            raise ValueError("Начало регистрации должно быть раньше окончания")
        if self.variants_count < 1:
            raise ValueError("Должен быть хотя бы один вариант")
        if self.max_score < 1:
            raise ValueError("Максимальный балл должен быть положительным")
        if self.is_special and self.special_tours_count is None:
            raise ValueError("Для особой олимпиады нужно указать количество туров")
        if self.special_tours_count is not None and self.special_tours_count < 1:
            raise ValueError("Количество туров должно быть положительным")
        if self.is_special and self.special_tour_modes is not None and self.special_tours_count is not None:
            if len(self.special_tour_modes) != self.special_tours_count:
                raise ValueError("Количество режимов туров должно совпадать с количеством туров")
            allowed_modes = {"individual", "individual_captains", "team"}
            invalid_modes = [mode for mode in self.special_tour_modes if mode not in allowed_modes]
            if invalid_modes:
                raise ValueError(
                    f"Недопустимые режимы туров: {', '.join(invalid_modes)}. "
                    f"Разрешены: {', '.join(sorted(allowed_modes))}"
                )
        if self.is_special and isinstance(self.special_settings, dict):
            seat_matrix_columns = self.special_settings.get("seat_matrix_columns")
            if seat_matrix_columns is not None:
                try:
                    parsed_columns = int(seat_matrix_columns)
                except (TypeError, ValueError):
                    raise ValueError("special_settings.seat_matrix_columns must be an integer")
                if parsed_columns < 1:
                    raise ValueError("special_settings.seat_matrix_columns must be >= 1")

            captains_room_id = self.special_settings.get("captains_room_id")
            if captains_room_id is not None:
                try:
                    UUID(str(captains_room_id))
                except (TypeError, ValueError):
                    raise ValueError("special_settings.captains_room_id must be a valid UUID")

            for default_key in ("default_seats_per_table", "team_default_seats_per_table"):
                raw_default = self.special_settings.get(default_key)
                if raw_default is None:
                    continue
                try:
                    parsed_default = int(raw_default)
                except (TypeError, ValueError):
                    raise ValueError(f"special_settings.{default_key} must be an integer")
                if parsed_default < 1:
                    raise ValueError(f"special_settings.{default_key} must be >= 1")

            for layout_key in ("room_layouts", "team_room_layouts"):
                raw_layouts = self.special_settings.get(layout_key)
                if raw_layouts is None:
                    continue
                if not isinstance(raw_layouts, dict):
                    raise ValueError(f"special_settings.{layout_key} must be an object")
                for room_id, room_layout in raw_layouts.items():
                    try:
                        UUID(str(room_id))
                    except (TypeError, ValueError):
                        raise ValueError(f"special_settings.{layout_key} contains invalid room id: {room_id}")
                    if not isinstance(room_layout, dict):
                        raise ValueError(f"special_settings.{layout_key}.{room_id} must be an object")
                    raw_seats_per_table = room_layout.get("seats_per_table")
                    try:
                        parsed_seats_per_table = int(raw_seats_per_table)
                    except (TypeError, ValueError):
                        raise ValueError(
                            f"special_settings.{layout_key}.{room_id}.seats_per_table must be an integer"
                        )
                    if parsed_seats_per_table < 1:
                        raise ValueError(
                            f"special_settings.{layout_key}.{room_id}.seats_per_table must be >= 1"
                        )
                    raw_seat_matrix_columns = room_layout.get("seat_matrix_columns")
                    if raw_seat_matrix_columns is not None:
                        try:
                            parsed_seat_matrix_columns = int(raw_seat_matrix_columns)
                        except (TypeError, ValueError):
                            raise ValueError(
                                f"special_settings.{layout_key}.{room_id}.seat_matrix_columns must be an integer"
                            )
                        if parsed_seat_matrix_columns < 1:
                            raise ValueError(
                                f"special_settings.{layout_key}.{room_id}.seat_matrix_columns must be >= 1"
                            )

            raw_team_table_merges = self.special_settings.get("team_table_merges")
            if raw_team_table_merges is not None:
                if not isinstance(raw_team_table_merges, dict):
                    raise ValueError("special_settings.team_table_merges must be an object")
                for tour_key, rooms_payload in raw_team_table_merges.items():
                    try:
                        parsed_tour = int(str(tour_key))
                    except (TypeError, ValueError):
                        raise ValueError("special_settings.team_table_merges keys must be tour numbers")
                    if parsed_tour < 1:
                        raise ValueError("special_settings.team_table_merges tour number must be >= 1")
                    if not isinstance(rooms_payload, dict):
                        raise ValueError(
                            f"special_settings.team_table_merges.{tour_key} must be an object mapping room_id to groups"
                        )
                    for room_id, groups_payload in rooms_payload.items():
                        try:
                            UUID(str(room_id))
                        except (TypeError, ValueError):
                            raise ValueError(
                                f"special_settings.team_table_merges.{tour_key} contains invalid room id: {room_id}"
                            )
                        if not isinstance(groups_payload, list):
                            raise ValueError(
                                f"special_settings.team_table_merges.{tour_key}.{room_id} must be a list of groups"
                            )
                        used_tables: set[int] = set()
                        for group in groups_payload:
                            if not isinstance(group, list):
                                raise ValueError(
                                    f"special_settings.team_table_merges.{tour_key}.{room_id} group must be a list"
                                )
                            if len(group) < 2:
                                raise ValueError(
                                    f"special_settings.team_table_merges.{tour_key}.{room_id} group must contain at least 2 tables"
                                )
                            normalized_group: set[int] = set()
                            for table_number in group:
                                if not isinstance(table_number, int) or table_number < 1:
                                    raise ValueError(
                                        f"special_settings.team_table_merges.{tour_key}.{room_id} must contain only positive table numbers"
                                    )
                                normalized_group.add(table_number)
                            if len(normalized_group) < 2:
                                raise ValueError(
                                    f"special_settings.team_table_merges.{tour_key}.{room_id} group must contain at least 2 unique tables"
                                )
                            overlap = used_tables.intersection(normalized_group)
                            if overlap:
                                raise ValueError(
                                    f"special_settings.team_table_merges.{tour_key}.{room_id} has duplicated table numbers across groups: {sorted(overlap)}"
                                )
                            used_tables.update(normalized_group)

            tours = self.special_settings.get("tours")
            if tours is not None:
                if not isinstance(tours, list):
                    raise ValueError("special_settings.tours must be a list")
                if self.special_tours_count is not None and len(tours) != self.special_tours_count:
                    raise ValueError("special_settings.tours length must match special_tours_count")
                allowed_modes = {"individual", "individual_captains", "team"}
                for idx, tour in enumerate(tours, start=1):
                    if not isinstance(tour, dict):
                        raise ValueError(f"special_settings.tours[{idx}] must be an object")
                    mode = str(tour.get("mode") or "")
                    if mode not in allowed_modes:
                        raise ValueError(
                            f"special_settings.tours[{idx}].mode must be one of: individual, individual_captains, team"
                        )
                    raw_tasks = tour.get("task_numbers", [])
                    if not isinstance(raw_tasks, list) or len(raw_tasks) == 0:
                        raise ValueError(f"special_settings.tours[{idx}].task_numbers must contain at least one task")
                    for task in raw_tasks:
                        if not isinstance(task, int) or task < 1:
                            raise ValueError(
                                f"special_settings.tours[{idx}].task_numbers must contain only positive integers"
                            )


    def open_registration(self):
        """Open registration for participants."""
        if self.status != CompetitionStatus.DRAFT:
            raise ValueError("Открыть регистрацию можно только из статуса черновик")
        self.status = CompetitionStatus.REGISTRATION_OPEN
        self.updated_at = datetime.utcnow()

    def start_competition(self):
        """Start the competition (admission begins)."""
        if self.status != CompetitionStatus.REGISTRATION_OPEN:
            raise ValueError("Начать можно только из статуса открытая регистрация")
        self.status = CompetitionStatus.IN_PROGRESS
        self.updated_at = datetime.utcnow()

    def start_checking(self):
        """Move to checking phase (all submissions in, scoring begins)."""
        if self.status != CompetitionStatus.IN_PROGRESS:
            raise ValueError("Начать проверку можно только из статуса в процессе")
        self.status = CompetitionStatus.CHECKING
        self.updated_at = datetime.utcnow()

    def publish_results(self):
        """Publish competition results to participants."""
        if self.status != CompetitionStatus.CHECKING:
            raise ValueError("Опубликовать можно только из статуса проверка")
        self.status = CompetitionStatus.PUBLISHED
        self.updated_at = datetime.utcnow()

    @property
    def is_registration_open(self) -> bool:
        """Check if registration is currently open.

        Registration is open if the status is REGISTRATION_OPEN.
        The admin controls this status manually, so time-based checks
        are not enforced here.
        """
        return self.status == CompetitionStatus.REGISTRATION_OPEN

    @property
    def is_in_progress(self) -> bool:
        """Check if competition is in progress."""
        return self.status == CompetitionStatus.IN_PROGRESS

    @property
    def are_results_published(self) -> bool:
        """Check if results are published."""
        return self.status == CompetitionStatus.PUBLISHED
