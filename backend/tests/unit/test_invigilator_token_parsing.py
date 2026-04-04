"""Unit tests for invigilator token parsing and special-sheet helpers."""

from types import SimpleNamespace
from uuid import UUID, uuid4

from olimpqr.domain.entities import AnswerSheet
from olimpqr.domain.value_objects import SheetKind
from olimpqr.domain.value_objects.token import TokenHash

from olimpqr.presentation.api.v1.invigilator import (
    _compute_next_special_extra_index,
    _extract_attempt_id_from_token,
    _extract_special_tours,
    _normalize_sheet_token,
)


ATTEMPT_ID = "3a63cf99-c06a-4767-8efa-dca3751905c3"


def test_extract_attempt_id_from_direct_token():
    token = f"attempt:{ATTEMPT_ID}:tour:1:task:2"
    assert _extract_attempt_id_from_token(token) == UUID(ATTEMPT_ID)


def test_extract_attempt_id_from_legacy_token_without_attempt_prefix():
    token = f"{ATTEMPT_ID}:tour:2:task:5"
    assert _extract_attempt_id_from_token(token) == UUID(ATTEMPT_ID)


def test_extract_attempt_id_from_url_path_token():
    token = f"https://example.org/qr/attempt/{ATTEMPT_ID}/tour/1"
    normalized = _normalize_sheet_token(token)
    assert _extract_attempt_id_from_token(normalized) == UUID(ATTEMPT_ID)


def test_normalize_token_from_query_param():
    token = f"https://example.org/scan?sheet_token=attempt%3A{ATTEMPT_ID}%3Atour%3A3"
    normalized = _normalize_sheet_token(token)
    assert normalized == f"attempt:{ATTEMPT_ID}:tour:3"


def test_normalize_strips_hidden_chars():
    token = f"\ufeff\u200battempt:{ATTEMPT_ID}:tour:1:task:1\u200b"
    normalized = _normalize_sheet_token(token)
    assert normalized == f"attempt:{ATTEMPT_ID}:tour:1:task:1"


def test_extract_special_tours_from_settings():
    competition = SimpleNamespace(
        is_special=True,
        special_tours_count=3,
        special_tour_modes=["individual", "team", "individual_captains"],
        special_settings={
            "tours": [
                {"tour_number": 1, "mode": "individual", "task_numbers": [1, 2]},
                {"tour_number": 2, "mode": "team", "task_numbers": [5]},
            ]
        },
    )
    tours = _extract_special_tours(competition)
    assert tours == [
        {"tour_number": 1, "mode": "individual", "task_numbers": [1, 2]},
        {"tour_number": 2, "mode": "team", "task_numbers": [5]},
    ]


def test_compute_next_special_extra_index():
    attempt_id = uuid4()

    def make_sheet(path: str) -> AnswerSheet:
        return AnswerSheet(
            attempt_id=attempt_id,
            sheet_token_hash=TokenHash(value="a" * 64),
            kind=SheetKind.EXTRA,
            pdf_file_path=path,
        )

    sheets = [
        make_sheet(f"sheets/special_extra/{attempt_id}/tour_2/task_5/extra_1_x.docx"),
        make_sheet(f"sheets/special_extra/{attempt_id}/tour_2/task_5/extra_2_y.docx"),
        make_sheet(f"sheets/special_extra/{attempt_id}/tour_2/task_4/extra_7_z.docx"),
    ]
    next_index = _compute_next_special_extra_index(sheets, attempt_id=attempt_id, tour_number=2, task_number=5)
    assert next_index == 3
