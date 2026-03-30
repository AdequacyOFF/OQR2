"""Assign seat use case - core seating algorithm."""

from dataclasses import dataclass
from uuid import UUID

from ....domain.entities import SeatAssignment
from ....domain.repositories import (
    ParticipantRepository,
    RegistrationRepository,
    RoomRepository,
    SeatAssignmentRepository,
)


@dataclass
class _SeatOccupant:
    """Occupied seat context used by special seating heuristics."""

    seat_number: int
    institution_id: UUID | None
    institution_branch_key: str | None
    is_captain: bool


@dataclass
class AssignSeatResult:
    seat_assignment_id: UUID
    room_id: UUID
    room_name: str
    seat_number: int
    variant_number: int


class AssignSeatUseCase:
    """Assign a seat to a participant for a competition.

    Base algorithm:
    1. Check if seat already assigned (idempotent)
    2. Evaluate available rooms and candidate seats
    3. Minimize conflicts (special rules first), then institution density
    4. Assign seat and variant

    Special olympiad additions:
    - For `individual` and `individual_captains` mode:
      avoid placing participants from the same institution branch
      in the local 3x3 neighborhood (approximated by grid columns).
      Also avoid placing same-branch participants at the same table.
    - For `individual_captains` mode with `captains_room_id` configured:
      prefer placing captains in that room and non-captains outside it.
    """

    def __init__(
        self,
        room_repository: RoomRepository,
        seat_assignment_repository: SeatAssignmentRepository,
        registration_repository: RegistrationRepository,
        participant_repository: ParticipantRepository,
    ):
        self.room_repo = room_repository
        self.seat_repo = seat_assignment_repository
        self.registration_repo = registration_repository
        self.participant_repo = participant_repository

    async def execute(
        self,
        registration_id: UUID,
        competition_id: UUID,
        variants_count: int,
        competition=None,
    ) -> AssignSeatResult | None:
        # 1. Check if already assigned (idempotent)
        existing = await self.seat_repo.get_by_registration(registration_id)
        if existing:
            room = await self.room_repo.get_by_id(existing.room_id)
            return AssignSeatResult(
                seat_assignment_id=existing.id,
                room_id=existing.room_id,
                room_name=room.name if room else "?",
                seat_number=existing.seat_number,
                variant_number=existing.variant_number,
            )

        # 2. Get rooms for competition
        rooms = await self.room_repo.get_by_competition(competition_id)
        if not rooms:
            return None  # No rooms configured, skip seating

        # 3. Get participant and current mode context
        registration = await self.registration_repo.get_by_id(registration_id)
        if not registration:
            raise ValueError("Регистрация не найдена")

        participant = await self.participant_repo.get_by_id(registration.participant_id)
        if not participant:
            raise ValueError("Участник не найден")

        institution_id = participant.institution_id
        branch_key = self._participant_branch_key(participant)
        special_mode = self._resolve_special_mode(competition)
        apply_neighborhood_rule = special_mode in {"individual", "individual_captains"}
        seat_columns = self._resolve_seat_columns(competition)
        captains_room_id = self._resolve_captains_room_id(competition)
        is_captain = bool(getattr(participant, "is_captain", False))

        non_full_rooms = []
        for room in rooms:
            occupied = await self.seat_repo.count_by_room(room.id)
            if occupied < room.capacity:
                non_full_rooms.append(room)

        if not non_full_rooms:
            raise ValueError("Нет свободных мест ни в одной аудитории")

        candidate_rooms = self._filter_candidate_rooms_for_captains(
            rooms=non_full_rooms,
            captains_room_id=captains_room_id,
            is_captain=is_captain,
            special_mode=special_mode,
        )
        if not candidate_rooms:
            candidate_rooms = non_full_rooms

        # 4. Evaluate all candidate seats
        best_room = None
        best_seat_number = None
        best_score: tuple[int, int, int, int, int, int] | None = None

        registration_cache: dict[UUID, object | None] = {}
        participant_cache: dict[UUID, object | None] = {}

        for room in candidate_rooms:
            room_assignments = await self.seat_repo.get_by_room(room.id)
            taken_seats = {a.seat_number for a in room_assignments}
            occupants = await self._build_occupants(
                room_assignments=room_assignments,
                registration_cache=registration_cache,
                participant_cache=participant_cache,
            )
            same_institution_in_room = (
                sum(1 for o in occupants if institution_id and o.institution_id == institution_id)
                if institution_id
                else 0
            )
            seats_per_table = self._resolve_room_seats_per_table(
                competition=competition,
                room_id=room.id,
                special_mode=special_mode,
            )
            free_seats = room.capacity - len(taken_seats)

            for seat_number in range(1, room.capacity + 1):
                if seat_number in taken_seats:
                    continue

                neighborhood_conflicts = (
                    self._count_neighborhood_branch_conflicts(
                        seat_number=seat_number,
                        target_branch_key=branch_key,
                        occupants=occupants,
                        columns=seat_columns,
                    )
                    if apply_neighborhood_rule
                    else 0
                )
                table_conflicts = (
                    self._count_same_table_branch_conflicts(
                        seat_number=seat_number,
                        target_branch_key=branch_key,
                        occupants=occupants,
                        seats_per_table=seats_per_table,
                    )
                    if apply_neighborhood_rule
                    else 0
                )

                # Lower tuple is better.
                score = (
                    neighborhood_conflicts,
                    table_conflicts,
                    same_institution_in_room,
                    0 if free_seats > 0 else 1,
                    -free_seats,
                    seat_number,
                )
                if best_score is None or score < best_score:
                    best_score = score
                    best_room = room
                    best_seat_number = seat_number

        if not best_room:
            raise ValueError("Нет свободных мест ни в одной аудитории")

        seat_number = best_seat_number if best_seat_number is not None else 1

        # Keep historical formula for compatibility.
        variant_number = (seat_number % variants_count) + 1

        assignment = SeatAssignment(
            registration_id=registration_id,
            room_id=best_room.id,
            seat_number=seat_number,
            variant_number=variant_number,
        )
        await self.seat_repo.create(assignment)

        return AssignSeatResult(
            seat_assignment_id=assignment.id,
            room_id=best_room.id,
            room_name=best_room.name,
            seat_number=seat_number,
            variant_number=variant_number,
        )

    @staticmethod
    def _participant_branch_key(participant) -> str | None:
        if not participant or not getattr(participant, "institution_id", None):
            return None
        location = (getattr(participant, "institution_location", None) or "").strip().lower()
        if location:
            return f"{participant.institution_id}:{location}"
        return str(participant.institution_id)

    @staticmethod
    def _resolve_special_mode(competition) -> str | None:
        if not competition or not getattr(competition, "is_special", False):
            return None
        settings_payload = getattr(competition, "special_settings", None) or {}
        tours = settings_payload.get("tours")
        if isinstance(tours, list) and tours:
            first = tours[0]
            if isinstance(first, dict):
                mode = first.get("mode")
                if isinstance(mode, str):
                    return mode
        modes = getattr(competition, "special_tour_modes", None) or []
        if modes:
            return str(modes[0])
        return None

    @staticmethod
    def _resolve_seat_columns(competition) -> int:
        settings_payload = getattr(competition, "special_settings", None) or {}
        raw_value = settings_payload.get("seat_matrix_columns", 3)
        try:
            columns = int(raw_value)
        except (TypeError, ValueError):
            columns = 3
        return max(columns, 1)

    @staticmethod
    def _resolve_room_seats_per_table(competition, room_id: UUID, special_mode: str | None) -> int:
        settings_payload = getattr(competition, "special_settings", None) or {}
        room_key = str(room_id)
        is_team_mode = special_mode == "team"

        def _extract(mapping) -> int | None:
            if not isinstance(mapping, dict):
                return None
            room_payload = mapping.get(room_key)
            if not isinstance(room_payload, dict):
                return None
            raw = room_payload.get("seats_per_table")
            try:
                parsed = int(raw)
            except (TypeError, ValueError):
                return None
            return parsed if parsed > 0 else None

        raw_room_layouts = settings_payload.get("room_layouts")
        raw_team_layouts = settings_payload.get("team_room_layouts")
        value = _extract(raw_team_layouts if is_team_mode else raw_room_layouts)
        if value is None and is_team_mode:
            value = _extract(raw_room_layouts)
        if value is None:
            raw_default = (
                settings_payload.get("team_default_seats_per_table")
                if is_team_mode
                else settings_payload.get("default_seats_per_table")
            )
            try:
                value = int(raw_default)
            except (TypeError, ValueError):
                value = 1
        return max(value, 1)

    @staticmethod
    def _resolve_captains_room_id(competition) -> UUID | None:
        settings_payload = getattr(competition, "special_settings", None) or {}
        raw_value = settings_payload.get("captains_room_id")
        if not raw_value:
            return None
        try:
            return UUID(str(raw_value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _filter_candidate_rooms_for_captains(rooms, captains_room_id: UUID | None, is_captain: bool, special_mode: str | None):
        if special_mode != "individual_captains" or captains_room_id is None:
            return rooms
        if is_captain:
            preferred = [room for room in rooms if room.id == captains_room_id]
            return preferred or rooms
        preferred = [room for room in rooms if room.id != captains_room_id]
        return preferred or rooms

    async def _build_occupants(
        self,
        room_assignments,
        registration_cache: dict[UUID, object | None],
        participant_cache: dict[UUID, object | None],
    ) -> list[_SeatOccupant]:
        occupants: list[_SeatOccupant] = []
        for assignment in room_assignments:
            registration = registration_cache.get(assignment.registration_id)
            if registration is None:
                registration = await self.registration_repo.get_by_id(assignment.registration_id)
                registration_cache[assignment.registration_id] = registration
            if not registration:
                continue
            participant = participant_cache.get(registration.participant_id)
            if participant is None:
                participant = await self.participant_repo.get_by_id(registration.participant_id)
                participant_cache[registration.participant_id] = participant
            if not participant:
                continue
            occupants.append(
                _SeatOccupant(
                    seat_number=assignment.seat_number,
                    institution_id=getattr(participant, "institution_id", None),
                    institution_branch_key=self._participant_branch_key(participant),
                    is_captain=bool(getattr(participant, "is_captain", False)),
                )
            )
        return occupants

    @staticmethod
    def _count_neighborhood_branch_conflicts(
        seat_number: int,
        target_branch_key: str | None,
        occupants: list[_SeatOccupant],
        columns: int,
    ) -> int:
        if not target_branch_key:
            return 0
        row = (seat_number - 1) // columns
        col = (seat_number - 1) % columns
        conflicts = 0
        for occupant in occupants:
            if occupant.institution_branch_key != target_branch_key:
                continue
            o_row = (occupant.seat_number - 1) // columns
            o_col = (occupant.seat_number - 1) % columns
            if abs(o_row - row) <= 1 and abs(o_col - col) <= 1:
                conflicts += 1
        return conflicts

    @staticmethod
    def _count_same_table_branch_conflicts(
        seat_number: int,
        target_branch_key: str | None,
        occupants: list[_SeatOccupant],
        seats_per_table: int,
    ) -> int:
        if not target_branch_key:
            return 0
        table_index = (seat_number - 1) // max(seats_per_table, 1)
        conflicts = 0
        for occupant in occupants:
            if occupant.institution_branch_key != target_branch_key:
                continue
            occupant_table_index = (occupant.seat_number - 1) // max(seats_per_table, 1)
            if occupant_table_index == table_index:
                conflicts += 1
        return conflicts
