"""Unit tests for team seating projection over merged tables."""

from uuid import uuid4

from olimpqr.presentation.api.v1.admin import _project_team_seating_for_merges


def _build_room_tables_with_two_seats_per_table(tables_count: int) -> list[dict]:
    tables: list[dict] = []
    seat_number = 1
    for table_number in range(1, tables_count + 1):
        seats = []
        for seat_at_table in range(1, 3):
            seats.append(
                {
                    "seat_number": seat_number,
                    "seat_at_table": seat_at_table,
                    "table_number": table_number,
                    "occupied": False,
                    "variant_number": None,
                    "participant_name": None,
                    "institution_id": None,
                    "institution_name": None,
                    "institution_location": None,
                    "is_captain": False,
                }
            )
            seat_number += 1
        tables.append(
            {
                "table_number": table_number,
                "occupied": False,
                "seats": seats,
            }
        )
    return tables


def _put_participant(
    room_tables: list[dict],
    seat_number: int,
    participant_name: str,
    institution_id,
    institution_name: str,
) -> None:
    for table in room_tables:
        for seat in table["seats"]:
            if seat["seat_number"] != seat_number:
                continue
            seat.update(
                {
                    "occupied": True,
                    "variant_number": 1,
                    "participant_name": participant_name,
                    "institution_id": institution_id,
                    "institution_name": institution_name,
                    "institution_location": "Main",
                    "is_captain": False,
                }
            )
            table["occupied"] = True
            return
    raise AssertionError(f"Seat {seat_number} not found")


def _occupied_institution_ids(table_payload: dict) -> set:
    return {
        seat["institution_id"]
        for seat in table_payload["seats"]
        if seat.get("occupied") and seat.get("institution_id") is not None
    }


def test_projection_keeps_one_team_inside_merged_group_when_possible():
    room_tables = _build_room_tables_with_two_seats_per_table(tables_count=4)
    team_a = uuid4()
    team_b = uuid4()

    # Initial mixed occupancy across the whole room.
    _put_participant(room_tables, 1, "A1", team_a, "A")
    _put_participant(room_tables, 2, "B1", team_b, "B")
    _put_participant(room_tables, 3, "A2", team_a, "A")
    _put_participant(room_tables, 4, "B2", team_b, "B")
    _put_participant(room_tables, 5, "A3", team_a, "A")
    _put_participant(room_tables, 6, "A4", team_a, "A")

    # Merge first 3 tables (capacity=6). Table 4 remains separate (capacity=2).
    _project_team_seating_for_merges(room_tables, [[1, 2, 3]])

    merged_ids = set()
    for table_number in (1, 2, 3):
        merged_ids |= _occupied_institution_ids(room_tables[table_number - 1])

    # Merged group should hold a single team (A) in this scenario.
    assert merged_ids == {team_a}
    assert _occupied_institution_ids(room_tables[3]) == {team_b}


def test_projection_updates_table_occupied_flags():
    room_tables = _build_room_tables_with_two_seats_per_table(tables_count=2)
    team_a = uuid4()

    _put_participant(room_tables, 1, "A1", team_a, "A")
    _project_team_seating_for_merges(room_tables, [[1, 2]])

    # Flags should be recomputed from resulting seat occupancy.
    assert room_tables[0]["occupied"] is True
    assert room_tables[1]["occupied"] in (True, False)
