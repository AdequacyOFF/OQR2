"""Unit tests for the seating assignment algorithm."""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from olimpqr.application.use_cases.seating.assign_seat import AssignSeatUseCase
from olimpqr.domain.entities import Competition, Participant, Registration, Room, SeatAssignment


@pytest.mark.asyncio
class TestSeatingAlgorithm:
    def _make_room(self, competition_id, capacity=30, name="R1"):
        return Room(id=uuid4(), competition_id=competition_id, name=name, capacity=capacity)

    def _make_participant(self, institution_id=None, institution_location=None, is_captain=False):
        return Participant(
            user_id=uuid4(),
            full_name="Test",
            school="School",
            grade=10,
            institution_id=institution_id,
            institution_location=institution_location,
            is_captain=is_captain,
        )

    def _make_registration(self, participant_id, competition_id):
        return Registration(
            id=uuid4(),
            participant_id=participant_id,
            competition_id=competition_id,
        )

    def _make_competition(self, is_special=False, special_tour_modes=None, special_settings=None):
        now = datetime.utcnow()
        return Competition(
            name="Comp",
            date=date.today(),
            registration_start=now - timedelta(days=1),
            registration_end=now + timedelta(days=1),
            variants_count=4,
            max_score=100,
            created_by=uuid4(),
            is_special=is_special,
            special_tours_count=(len(special_tour_modes) if special_tour_modes else (1 if is_special else None)),
            special_tour_modes=special_tour_modes,
            special_settings=special_settings,
        )

    async def test_assigns_to_room_with_lower_same_institution_density(self):
        comp = self._make_competition()
        inst_id = uuid4()

        room1 = self._make_room(comp.id, name="R1")
        room2 = self._make_room(comp.id, name="R2")

        target_participant = self._make_participant(institution_id=inst_id)
        target_registration = self._make_registration(target_participant.id, comp.id)

        existing_same_participant = self._make_participant(institution_id=inst_id)
        existing_same_registration = self._make_registration(existing_same_participant.id, comp.id)
        existing_same_assignment = SeatAssignment(
            registration_id=existing_same_registration.id,
            room_id=room1.id,
            seat_number=1,
            variant_number=1,
        )

        room_repo = AsyncMock()
        room_repo.get_by_competition.return_value = [room1, room2]
        room_repo.get_by_id.return_value = room2

        seat_repo = AsyncMock()
        seat_repo.get_by_registration.return_value = None
        seat_repo.count_by_room.side_effect = [1, 0]
        seat_repo.get_by_room.side_effect = [[existing_same_assignment], []]
        seat_repo.create.return_value = None

        reg_repo = AsyncMock()

        async def reg_by_id(registration_id):
            mapping = {
                target_registration.id: target_registration,
                existing_same_registration.id: existing_same_registration,
            }
            return mapping.get(registration_id)

        reg_repo.get_by_id.side_effect = reg_by_id

        part_repo = AsyncMock()

        async def part_by_id(participant_id):
            mapping = {
                target_participant.id: target_participant,
                existing_same_participant.id: existing_same_participant,
            }
            return mapping.get(participant_id)

        part_repo.get_by_id.side_effect = part_by_id

        uc = AssignSeatUseCase(room_repo, seat_repo, reg_repo, part_repo)
        result = await uc.execute(target_registration.id, comp.id, variants_count=4, competition=comp)

        assert result is not None
        assert result.room_id == room2.id

    async def test_idempotent_returns_existing(self):
        existing = SeatAssignment(
            registration_id=uuid4(),
            room_id=uuid4(),
            seat_number=3,
            variant_number=2,
        )

        room_repo = AsyncMock()
        room_repo.get_by_id.return_value = Room(
            id=existing.room_id,
            competition_id=uuid4(),
            name="R1",
            capacity=30,
        )

        seat_repo = AsyncMock()
        seat_repo.get_by_registration.return_value = existing

        reg_repo = AsyncMock()
        part_repo = AsyncMock()

        uc = AssignSeatUseCase(room_repo, seat_repo, reg_repo, part_repo)
        result = await uc.execute(existing.registration_id, uuid4(), variants_count=4)

        assert result.seat_number == 3
        assert result.variant_number == 2

    async def test_returns_none_if_no_rooms(self):
        comp = self._make_competition()
        participant = self._make_participant()
        registration = self._make_registration(participant.id, comp.id)

        room_repo = AsyncMock()
        room_repo.get_by_competition.return_value = []

        seat_repo = AsyncMock()
        seat_repo.get_by_registration.return_value = None

        reg_repo = AsyncMock()
        reg_repo.get_by_id.return_value = registration

        part_repo = AsyncMock()
        part_repo.get_by_id.return_value = participant

        uc = AssignSeatUseCase(room_repo, seat_repo, reg_repo, part_repo)
        result = await uc.execute(registration.id, comp.id, variants_count=4)

        assert result is None

    async def test_variant_assignment(self):
        comp = self._make_competition()
        room = self._make_room(comp.id, capacity=100)
        participant = self._make_participant()
        registration = self._make_registration(participant.id, comp.id)

        room_repo = AsyncMock()
        room_repo.get_by_competition.return_value = [room]
        room_repo.get_by_id.return_value = room

        seat_repo = AsyncMock()
        seat_repo.get_by_registration.return_value = None
        seat_repo.count_by_room.return_value = 0
        seat_repo.get_by_room.return_value = []
        seat_repo.create.return_value = None

        reg_repo = AsyncMock()
        reg_repo.get_by_id.return_value = registration

        part_repo = AsyncMock()
        part_repo.get_by_id.return_value = participant

        uc = AssignSeatUseCase(room_repo, seat_repo, reg_repo, part_repo)
        result = await uc.execute(registration.id, comp.id, variants_count=4, competition=comp)

        assert result is not None
        assert result.seat_number == 1
        assert result.variant_number == (1 % 4) + 1

    async def test_special_mode_avoids_same_branch_in_local_3x3(self):
        comp = self._make_competition(
            is_special=True,
            special_tour_modes=["individual"],
            special_settings={"seat_matrix_columns": 3, "tours": [{"mode": "individual", "task_numbers": [1]}]},
        )
        room = self._make_room(comp.id, capacity=4)

        inst_id = uuid4()
        target_participant = self._make_participant(institution_id=inst_id, institution_location="Moscow")
        target_registration = self._make_registration(target_participant.id, comp.id)

        existing_participant = self._make_participant(institution_id=inst_id, institution_location="Moscow")
        existing_registration = self._make_registration(existing_participant.id, comp.id)
        existing_assignment = SeatAssignment(
            registration_id=existing_registration.id,
            room_id=room.id,
            seat_number=1,
            variant_number=1,
        )

        room_repo = AsyncMock()
        room_repo.get_by_competition.return_value = [room]

        seat_repo = AsyncMock()
        seat_repo.get_by_registration.return_value = None
        seat_repo.count_by_room.return_value = 1
        seat_repo.get_by_room.return_value = [existing_assignment]
        seat_repo.create.return_value = None

        reg_repo = AsyncMock()

        async def reg_by_id(registration_id):
            mapping = {
                target_registration.id: target_registration,
                existing_registration.id: existing_registration,
            }
            return mapping.get(registration_id)

        reg_repo.get_by_id.side_effect = reg_by_id

        part_repo = AsyncMock()

        async def part_by_id(participant_id):
            mapping = {
                target_participant.id: target_participant,
                existing_participant.id: existing_participant,
            }
            return mapping.get(participant_id)

        part_repo.get_by_id.side_effect = part_by_id

        uc = AssignSeatUseCase(room_repo, seat_repo, reg_repo, part_repo)
        result = await uc.execute(target_registration.id, comp.id, variants_count=4, competition=comp)

        # Seat 2 is in 3x3 neighborhood with seat 1, seat 3 is not.
        assert result is not None
        assert result.seat_number == 3

    async def test_special_mode_avoids_same_branch_on_same_table(self):
        comp = self._make_competition(
            is_special=True,
            special_tour_modes=["individual"],
            special_settings={
                "seat_matrix_columns": 100,
                "room_layouts": {},
                "tours": [{"mode": "individual", "task_numbers": [1]}],
            },
        )
        room = self._make_room(comp.id, capacity=8)
        comp.special_settings["room_layouts"] = {
            str(room.id): {"seats_per_table": 4},
        }

        inst_id = uuid4()
        target_participant = self._make_participant(institution_id=inst_id, institution_location="Moscow")
        target_registration = self._make_registration(target_participant.id, comp.id)

        existing_participant = self._make_participant(institution_id=inst_id, institution_location="Moscow")
        existing_registration = self._make_registration(existing_participant.id, comp.id)
        existing_assignment = SeatAssignment(
            registration_id=existing_registration.id,
            room_id=room.id,
            seat_number=1,
            variant_number=1,
        )

        room_repo = AsyncMock()
        room_repo.get_by_competition.return_value = [room]

        seat_repo = AsyncMock()
        seat_repo.get_by_registration.return_value = None
        seat_repo.count_by_room.return_value = 1
        seat_repo.get_by_room.return_value = [existing_assignment]
        seat_repo.create.return_value = None

        reg_repo = AsyncMock()

        async def reg_by_id(registration_id):
            mapping = {
                target_registration.id: target_registration,
                existing_registration.id: existing_registration,
            }
            return mapping.get(registration_id)

        reg_repo.get_by_id.side_effect = reg_by_id

        part_repo = AsyncMock()

        async def part_by_id(participant_id):
            mapping = {
                target_participant.id: target_participant,
                existing_participant.id: existing_participant,
            }
            return mapping.get(participant_id)

        part_repo.get_by_id.side_effect = part_by_id

        uc = AssignSeatUseCase(room_repo, seat_repo, reg_repo, part_repo)
        result = await uc.execute(target_registration.id, comp.id, variants_count=4, competition=comp)

        assert result is not None
        # Seat #3 has no 3x3 conflict but remains at same table with #1.
        # Seat #5 is first seat on another table and should be preferred.
        assert result.seat_number == 5

    async def test_individual_captains_places_captain_in_captains_room(self):
        comp_id = uuid4()
        room_regular = self._make_room(comp_id, name="R1")
        room_captains = self._make_room(comp_id, name="CAP")

        comp = self._make_competition(
            is_special=True,
            special_tour_modes=["individual_captains"],
            special_settings={
                "captains_room_id": str(room_captains.id),
                "tours": [{"mode": "individual_captains", "task_numbers": [1]}],
            },
        )
        comp.id = comp_id
        room_regular.competition_id = comp_id
        room_captains.competition_id = comp_id

        participant = self._make_participant(institution_id=uuid4(), is_captain=True)
        registration = self._make_registration(participant.id, comp_id)

        room_repo = AsyncMock()
        room_repo.get_by_competition.return_value = [room_regular, room_captains]

        seat_repo = AsyncMock()
        seat_repo.get_by_registration.return_value = None
        seat_repo.count_by_room.side_effect = [0, 0]
        seat_repo.get_by_room.side_effect = [[], []]
        seat_repo.create.return_value = None

        reg_repo = AsyncMock()
        reg_repo.get_by_id.return_value = registration

        part_repo = AsyncMock()
        part_repo.get_by_id.return_value = participant

        uc = AssignSeatUseCase(room_repo, seat_repo, reg_repo, part_repo)
        result = await uc.execute(registration.id, comp_id, variants_count=4, competition=comp)

        assert result is not None
        assert result.room_id == room_captains.id

    def test_resolve_room_seats_per_table_uses_team_layout(self):
        room_id = uuid4()
        comp = self._make_competition(
            is_special=True,
            special_tour_modes=["team"],
            special_settings={
                "room_layouts": {str(room_id): {"seats_per_table": 2}},
                "team_room_layouts": {str(room_id): {"seats_per_table": 5}},
                "team_default_seats_per_table": 4,
                "tours": [{"mode": "team", "task_numbers": [1]}],
            },
        )

        team_value = AssignSeatUseCase._resolve_room_seats_per_table(comp, room_id, "team")
        individual_value = AssignSeatUseCase._resolve_room_seats_per_table(comp, room_id, "individual")

        assert team_value == 5
        assert individual_value == 2
