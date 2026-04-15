"""Get scoring progress use case."""

import asyncio
from dataclasses import dataclass, field
from uuid import UUID

from ....domain.repositories import (
    CompetitionRepository,
    RegistrationRepository,
    AttemptRepository,
    ParticipantRepository,
)
from ....domain.value_objects import RegistrationStatus


@dataclass
class TourProgressResult:
    tour_number: int
    task_scores: dict[str, int] | None
    tour_total: int | None
    tour_time: str | None = None


@dataclass
class ScoringProgressItemResult:
    registration_id: UUID
    participant_id: UUID
    participant_name: str
    participant_school: str
    variant_number: int | None
    attempt_id: UUID | None
    attempt_status: str | None
    tours: list[TourProgressResult] = field(default_factory=list)
    score_total: int | None = None
    is_captain: bool = False
    captains_task_by_tour: dict[int, int] = field(default_factory=dict)  # tour_number → captain bonus score total
    captains_task_scores_by_tour: dict[int, dict[str, int]] = field(default_factory=dict)  # tour_number → {task_num_str → score}


@dataclass
class ScoringProgressResult:
    competition_id: UUID
    competition_name: str
    is_special: bool
    tours_count: int
    items: list[ScoringProgressItemResult] = field(default_factory=list)
    total: int = 0


class GetScoringProgressUseCase:
    """Aggregate participant scoring status for a competition."""

    def __init__(
        self,
        competition_repository: CompetitionRepository,
        registration_repository: RegistrationRepository,
        attempt_repository: AttemptRepository,
        participant_repository: ParticipantRepository,
    ):
        self.competition_repository = competition_repository
        self.registration_repository = registration_repository
        self.attempt_repository = attempt_repository
        self.participant_repository = participant_repository

    async def execute(self, competition_id: UUID) -> ScoringProgressResult:
        competition = await self.competition_repository.get_by_id(competition_id)
        if not competition:
            raise ValueError("Олимпиада не найдена")

        registrations = await self.registration_repository.get_by_competition(
            competition_id, skip=0, limit=10000
        )
        registrations = [r for r in registrations if r.status != RegistrationStatus.CANCELLED]

        # Single JOIN query: all attempts for this competition keyed by registration_id
        attempts_list = await self.attempt_repository.get_by_competition(competition_id, limit=10000)
        attempts_by_reg: dict[UUID, object] = {a.registration_id: a for a in attempts_list}

        # Fetch all participants in parallel
        participants_list = await asyncio.gather(
            *[self.participant_repository.get_by_id(r.participant_id) for r in registrations]
        )
        participants_by_id = {p.id: p for p in participants_list if p}

        tours_count = competition.special_tours_count or 0

        items: list[ScoringProgressItemResult] = []
        for reg in registrations:
            participant = participants_by_id.get(reg.participant_id)
            if not participant:
                continue

            attempt = attempts_by_reg.get(reg.id)

            tour_progress: list[TourProgressResult] = []
            if competition.is_special and tours_count > 0:
                for tour_num in range(1, tours_count + 1):
                    task_scores: dict[str, int] | None = None
                    tour_total: int | None = None
                    tour_time: str | None = None
                    if attempt and attempt.task_scores:
                        raw = attempt.task_scores.get(str(tour_num))
                        if raw:
                            tour_time = raw.get("time") if isinstance(raw.get("time"), str) else None
                            task_scores = {str(k): int(v) for k, v in raw.items() if k != "time" and isinstance(v, int)}
                            tour_total = sum(task_scores.values())
                    tour_progress.append(TourProgressResult(
                        tour_number=tour_num,
                        task_scores=task_scores,
                        tour_total=tour_total,
                        tour_time=tour_time,
                    ))

            captains_task_by_tour: dict[int, int] = {}
            captains_task_scores_by_tour: dict[int, dict[str, int]] = {}
            if attempt and attempt.task_scores:
                for key, val in attempt.task_scores.items():
                    if key.startswith("cap_") and isinstance(val, dict):
                        try:
                            tour_n = int(key[4:])
                            cap_scores = {str(k): int(v) for k, v in val.items() if isinstance(v, int)}
                            captains_task_by_tour[tour_n] = sum(cap_scores.values())
                            captains_task_scores_by_tour[tour_n] = cap_scores
                        except (ValueError, TypeError):
                            pass

            items.append(ScoringProgressItemResult(
                registration_id=reg.id,
                participant_id=reg.participant_id,
                participant_name=participant.full_name,
                participant_school=participant.school,
                variant_number=attempt.variant_number if attempt else None,
                attempt_id=attempt.id if attempt else None,
                attempt_status=attempt.status.value if attempt else None,
                tours=tour_progress,
                score_total=attempt.score_total if attempt else None,
                is_captain=getattr(participant, 'is_captain', False) or False,
                captains_task_by_tour=captains_task_by_tour,
                captains_task_scores_by_tour=captains_task_scores_by_tour,
            ))

        return ScoringProgressResult(
            competition_id=competition.id,
            competition_name=competition.name,
            is_special=competition.is_special,
            tours_count=tours_count,
            items=items,
            total=len(items),
        )
