"""Approve admission and generate answer sheet use case."""

import random
from uuid import UUID, uuid4
from dataclasses import dataclass

from ....domain.entities import Attempt, AuditLog, AnswerSheet
from ....domain.value_objects import SheetKind
from ....domain.repositories import (
    EntryTokenRepository,
    RegistrationRepository,
    CompetitionRepository,
    AttemptRepository,
    AuditLogRepository,
    AnswerSheetRepository,
    RoomRepository,
    SeatAssignmentRepository,
    ParticipantRepository,
)
from ....domain.services import TokenService
from ....infrastructure.pdf import SheetGenerator
from ....infrastructure.storage import MinIOStorage
from ....config import settings
from ..seating import AssignSeatUseCase


@dataclass
class ApproveAdmissionResult:
    """Result of admission approval."""
    attempt_id: UUID
    variant_number: int
    pdf_url: str
    sheet_token: str  # raw token for QR code on sheet
    room_name: str | None = None
    seat_number: int | None = None


class ApproveAdmissionUseCase:
    """Approve admission: mark entry token used, generate answer sheet.

    Steps:
    1. Mark entry token as used (one-time use)
    2. Update registration status to ADMITTED
    3. Assign seat (room + seat + variant) via seating algorithm
    4. Fall back to random variant if no rooms configured
    5. Generate sheet token (for answer sheet QR)
    6. Create Attempt entity
    7. Create AnswerSheet(kind=primary)
    8. Generate PDF answer sheet with QR
    9. Upload PDF to MinIO
    10. Log action to audit log
    """

    def __init__(
        self,
        token_service: TokenService,
        entry_token_repository: EntryTokenRepository,
        registration_repository: RegistrationRepository,
        competition_repository: CompetitionRepository,
        attempt_repository: AttemptRepository,
        audit_log_repository: AuditLogRepository,
        answer_sheet_repository: AnswerSheetRepository,
        storage: MinIOStorage,
        sheet_generator: SheetGenerator,
        room_repository: RoomRepository | None = None,
        seat_assignment_repository: SeatAssignmentRepository | None = None,
        participant_repository: ParticipantRepository | None = None,
    ):
        self.token_service = token_service
        self.entry_token_repo = entry_token_repository
        self.registration_repo = registration_repository
        self.competition_repo = competition_repository
        self.attempt_repo = attempt_repository
        self.audit_log_repo = audit_log_repository
        self.answer_sheet_repo = answer_sheet_repository
        self.storage = storage
        self.sheet_generator = sheet_generator
        self.room_repo = room_repository
        self.seat_repo = seat_assignment_repository
        self.participant_repo = participant_repository

    async def execute(
        self,
        registration_id: UUID,
        raw_entry_token: str,
        admitter_user_id: UUID,
        ip_address: str | None = None,
    ) -> ApproveAdmissionResult:
        # 1. Verify token again (double-check)
        token_hash = self.token_service.hash_token(raw_entry_token)
        entry_token = await self.entry_token_repo.get_by_token_hash(token_hash.value)
        if not entry_token:
            raise ValueError("Токен не найден")
        if entry_token.is_used:
            raise ValueError("Токен уже использован")
        if entry_token.is_expired:
            raise ValueError("Срок действия токена истёк")
        if entry_token.registration_id != registration_id:
            raise ValueError("Токен не соответствует регистрации")

        # 2. Mark entry token as used
        entry_token.use()
        await self.entry_token_repo.update(entry_token)

        # 3. Update registration status
        registration = await self.registration_repo.get_by_id(registration_id)
        if not registration:
            raise ValueError("Регистрация не найдена")
        registration.admit()
        await self.registration_repo.update(registration)

        # 4. Get competition for variant count
        competition = await self.competition_repo.get_by_id(registration.competition_id)
        if not competition:
            raise ValueError("Олимпиада не найдена")

        # 5. Try seating algorithm if repos available
        room_name = None
        seat_number = None
        variant_number = None

        if self.room_repo and self.seat_repo and self.participant_repo:
            assign_seat_uc = AssignSeatUseCase(
                room_repository=self.room_repo,
                seat_assignment_repository=self.seat_repo,
                registration_repository=self.registration_repo,
                participant_repository=self.participant_repo,
            )
            seat_result = await assign_seat_uc.execute(
                registration_id=registration_id,
                competition_id=registration.competition_id,
                variants_count=competition.variants_count,
                competition=competition,
            )
            if seat_result:
                room_name = seat_result.room_name
                seat_number = seat_result.seat_number
                variant_number = seat_result.variant_number

        # Fall back to random variant if no seating
        if variant_number is None:
            variant_number = random.randint(1, competition.variants_count)

        # 6. Generate sheet token
        sheet_token = self.token_service.generate_token(
            size_bytes=settings.qr_token_size_bytes
        )

        # 7. Create attempt
        attempt = Attempt(
            id=uuid4(),
            registration_id=registration_id,
            variant_number=variant_number,
            sheet_token_hash=sheet_token.hash,
        )

        # 8. Generate PDF
        pdf_bytes = self.sheet_generator.generate_answer_sheet(
            competition_name=competition.name,
            variant_number=variant_number,
            sheet_token=sheet_token.raw,
        )

        # 9. Upload PDF to MinIO
        object_name = f"sheets/{competition.id}/{attempt.id}.pdf"
        self.storage.upload_file(
            bucket=settings.minio_bucket_sheets,
            object_name=object_name,
            data=pdf_bytes,
            content_type="application/pdf",
        )

        # 10. Save attempt with file path
        attempt.pdf_file_path = object_name
        await self.attempt_repo.create(attempt)

        # 11. Create AnswerSheet(kind=primary)
        answer_sheet = AnswerSheet(
            id=uuid4(),
            attempt_id=attempt.id,
            sheet_token_hash=sheet_token.hash,
            kind=SheetKind.PRIMARY,
            pdf_file_path=object_name,
        )
        await self.answer_sheet_repo.create(answer_sheet)

        # 12. Mark registration as completed (sheet given)
        registration.complete()
        await self.registration_repo.update(registration)

        # 13. Audit log
        audit = AuditLog.create_log(
            entity_type="registration",
            entity_id=registration_id,
            action="admitted",
            user_id=admitter_user_id,
            ip_address=ip_address,
            variant_number=variant_number,
            attempt_id=str(attempt.id),
            room_name=room_name,
            seat_number=seat_number,
        )
        await self.audit_log_repo.create(audit)

        # 14. Generate backend download URL
        pdf_url = f"admission/sheets/{attempt.id}/download"

        return ApproveAdmissionResult(
            attempt_id=attempt.id,
            variant_number=variant_number,
            pdf_url=pdf_url,
            sheet_token=sheet_token.raw,
            room_name=room_name,
            seat_number=seat_number,
        )
