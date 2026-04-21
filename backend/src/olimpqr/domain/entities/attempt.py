"""Attempt entity."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from ..value_objects import AttemptStatus, TokenHash


@dataclass
class Attempt:
    """Attempt entity - represents an answer sheet.

    Attributes:
        id: Unique identifier
        registration_id: Reference to Registration
        variant_number: Test variant number (1 to N)
        sheet_token_hash: HMAC hash of the sheet QR code token
        status: Attempt status
        score_total: Total score (None until scored)
        confidence: OCR confidence (None if manually scored)
        pdf_file_path: Path to PDF in MinIO storage
        created_at: When attempt was created
        updated_at: When attempt was last updated
    """
    registration_id: UUID
    variant_number: int
    sheet_token_hash: TokenHash
    id: UUID = field(default_factory=uuid4)
    status: AttemptStatus = AttemptStatus.PRINTED
    score_total: int | None = None
    confidence: float | None = None
    pdf_file_path: str | None = None
    task_scores: dict | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if not isinstance(self.sheet_token_hash, TokenHash):
            raise TypeError("sheet_token_hash must be a TokenHash instance")
        if self.variant_number < 1:
            raise ValueError("Номер варианта должен быть положительным")

    def mark_scanned(self):
        """Mark attempt as scanned (scan uploaded, OCR processing)."""
        if self.status != AttemptStatus.PRINTED:
            raise ValueError("Сканировать можно только напечатанные попытки")
        self.status = AttemptStatus.SCANNED
        self.updated_at = datetime.utcnow()

    def apply_score(self, score: int, confidence: float | None = None):
        """Apply score to attempt.

        Args:
            score: Total score value
            confidence: OCR confidence (None if manually entered)
        """
        if not self.status.can_apply_score:
            raise ValueError(f"Невозможно применить балл в статусе {self.status}")
        if score < 0:
            raise ValueError("Балл не может быть отрицательным")
        if confidence is not None and not (0.0 <= confidence <= 1.0):
            raise ValueError("Уверенность должна быть от 0.0 до 1.0")

        self.score_total = score
        self.confidence = confidence
        self.status = AttemptStatus.SCORED
        self.updated_at = datetime.utcnow()

    def publish(self):
        """Publish attempt (make visible in results)."""
        if not self.status.has_score:
            raise ValueError("Невозможно опубликовать попытку без балла")
        self.status = AttemptStatus.PUBLISHED
        self.updated_at = datetime.utcnow()

    def apply_task_scores(
        self,
        tour_number: int,
        scores: dict[int, int],
        tour_time: str | None = None,
        is_captains_task: bool = False,
    ) -> None:
        """Apply per-task scores for a specific tour.

        Updates task_scores JSON, recomputes score_total as the sum of
        all regular tour task scores. Captain task scores (is_captains_task=True)
        are stored under "captains_task" key and excluded from personal total.

        Args:
            tour_number: Tour number (1-based)
            scores: Mapping of task_number -> score for this tour
            tour_time: Optional per-participant time in hh.mm.ss format
            is_captains_task: When True, scores are stored under "captains_task" key
        """
        if tour_number < 1:
            raise ValueError("Номер тура должен быть положительным")
        for task_num, score in scores.items():
            if score < 0:
                raise ValueError(f"Балл за задание {task_num} не может быть отрицательным")

        current = dict(self.task_scores) if self.task_scores else {}

        if is_captains_task:
            # Captain task scores stored separately with tour reference — not counted in personal total
            cap_data: dict[str, int | str] = {str(k): v for k, v in scores.items()}
            if tour_time is not None:
                cap_data["time"] = tour_time
            elif (
                f"cap_{tour_number}" in current
                and isinstance(current[f"cap_{tour_number}"], dict)
                and "time" in current[f"cap_{tour_number}"]
            ):
                cap_data["time"] = current[f"cap_{tour_number}"]["time"]
            current[f"cap_{tour_number}"] = cap_data
        else:
            tour_data: dict[str, int | str] = {str(k): v for k, v in scores.items()}
            if tour_time is not None:
                tour_data["time"] = tour_time
            elif str(tour_number) in current and isinstance(current[str(tour_number)], dict) and "time" in current[str(tour_number)]:
                # Preserve existing time if not provided in this update
                tour_data["time"] = current[str(tour_number)]["time"]
            current[str(tour_number)] = tour_data

        self.task_scores = current

        # Recompute personal total — only numeric-keyed tours (cap_N keys excluded)
        total = 0
        for key, tdata in current.items():
            if not key.isdigit():
                continue  # skip "cap_N", "captains_task" (legacy), etc.
            if not isinstance(tdata, dict):
                continue
            for field_key, val in tdata.items():
                if field_key != "time" and isinstance(val, int):
                    total += val
        self.score_total = total
        self.status = AttemptStatus.SCORED
        self.updated_at = datetime.utcnow()

    def invalidate(self):
        """Invalidate attempt (cheating, technical issues, etc.)."""
        self.status = AttemptStatus.INVALIDATED
        self.updated_at = datetime.utcnow()

    @property
    def is_valid(self) -> bool:
        """Check if attempt is not invalidated."""
        return self.status != AttemptStatus.INVALIDATED

    @property
    def has_score(self) -> bool:
        """Check if score has been applied."""
        return self.score_total is not None
