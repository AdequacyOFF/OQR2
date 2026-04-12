"""Verify entry QR code use case."""

import datetime as dt
from uuid import UUID
from dataclasses import dataclass

from ....domain.repositories import (
    EntryTokenRepository,
    RegistrationRepository,
    ParticipantRepository,
    CompetitionRepository,
    InstitutionRepository,
    DocumentRepository,
)
from ....domain.services import TokenService


@dataclass
class VerifyEntryQRResult:
    """Result of entry QR verification."""
    registration_id: UUID
    participant_id: UUID
    participant_name: str
    participant_school: str
    participant_grade: int
    competition_name: str
    competition_id: UUID
    can_proceed: bool
    message: str
    institution_name: str | None = None
    institution_location: str | None = None
    is_captain: bool = False
    dob: dt.date | None = None
    position: str | None = None
    military_rank: str | None = None
    passport_series_number: str | None = None
    passport_issued_by: str | None = None
    passport_issued_date: dt.date | None = None
    military_booklet_number: str | None = None
    military_personal_number: str | None = None
    has_documents: bool = False


class VerifyEntryQRUseCase:
    """Verify an entry QR code scanned by an admitter.

    Checks:
    1. Compute HMAC hash of raw token
    2. Find entry_token by hash in DB
    3. Verify token not expired
    4. Verify token not already used
    5. Return participant + competition info for admitter confirmation
    """

    def __init__(
        self,
        token_service: TokenService,
        entry_token_repository: EntryTokenRepository,
        registration_repository: RegistrationRepository,
        participant_repository: ParticipantRepository,
        competition_repository: CompetitionRepository,
        institution_repository: InstitutionRepository | None = None,
        document_repository: DocumentRepository | None = None,
    ):
        self.token_service = token_service
        self.entry_token_repo = entry_token_repository
        self.registration_repo = registration_repository
        self.participant_repo = participant_repository
        self.competition_repo = competition_repository
        self.institution_repo = institution_repository
        self.document_repo = document_repository

    async def execute(self, raw_token: str) -> VerifyEntryQRResult:
        if not raw_token:
            raise ValueError("Токен не может быть пустым")

        # 1. Compute hash
        token_hash = self.token_service.hash_token(raw_token)

        # 2. Find entry token by hash
        entry_token = await self.entry_token_repo.get_by_token_hash(token_hash.value)
        if not entry_token:
            raise ValueError("Токен не найден")

        # 3. Check expiry
        if entry_token.is_expired:
            raise ValueError("Срок действия токена истёк")

        # 4. Check if already used
        if entry_token.is_used:
            raise ValueError("Токен уже использован")

        # 5. Get registration, participant, competition
        registration = await self.registration_repo.get_by_id(entry_token.registration_id)
        if not registration:
            raise ValueError("Регистрация не найдена")

        participant = await self.participant_repo.get_by_id(registration.participant_id)
        if not participant:
            raise ValueError("Участник не найден")

        competition = await self.competition_repo.get_by_id(registration.competition_id)
        if not competition:
            raise ValueError("Олимпиада не найдена")

        # 6. Get institution name if available
        institution_name = None
        if participant.institution_id and self.institution_repo:
            institution = await self.institution_repo.get_by_id(participant.institution_id)
            if institution:
                institution_name = institution.name

        # 7. Check if participant has documents
        has_documents = False
        if self.document_repo:
            docs = await self.document_repo.get_by_participant(participant.id)
            has_documents = len(docs) > 0

        common_fields = dict(
            registration_id=registration.id,
            participant_id=participant.id,
            participant_name=participant.full_name,
            participant_school=participant.school,
            participant_grade=participant.grade,
            competition_name=competition.name,
            competition_id=competition.id,
            institution_name=institution_name,
            institution_location=participant.institution_location,
            is_captain=participant.is_captain,
            dob=participant.dob,
            position=participant.position,
            military_rank=participant.military_rank,
            passport_series_number=participant.passport_series_number,
            passport_issued_by=participant.passport_issued_by,
            passport_issued_date=participant.passport_issued_date,
            military_booklet_number=participant.military_booklet_number,
            military_personal_number=participant.military_personal_number,
            has_documents=has_documents,
        )

        if not competition.is_in_progress:
            return VerifyEntryQRResult(
                can_proceed=False,
                message=f"Олимпиада не в процессе (статус: {competition.status.value})",
                **common_fields,
            )

        return VerifyEntryQRResult(
            can_proceed=True,
            message="Участник подтверждён. Можно выдать бланк.",
            **common_fields,
        )
