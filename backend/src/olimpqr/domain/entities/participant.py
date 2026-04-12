"""Participant entity."""

import datetime as dt
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class Participant:
    """Participant entity - extends User with participant-specific data.

    Attributes:
        id: Unique identifier
        user_id: Reference to User entity
        full_name: Participant's full name (shown in results)
        school: School name
        grade: School grade (e.g., 9, 10, 11)
        institution_id: Reference to Institution (nullable)
        dob: Date of birth (nullable)
        created_at: When participant profile was created
        updated_at: When participant profile was last updated
    """
    user_id: UUID
    full_name: str
    school: str
    grade: int | None = None
    id: UUID = field(default_factory=uuid4)
    institution_id: UUID | None = None
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
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if not self.full_name or len(self.full_name.strip()) < 2:
            raise ValueError("ФИО должно быть не менее 2 символов")
        if not self.school or len(self.school.strip()) < 2:
            raise ValueError("Название учебного учреждения должно быть не менее 2 символов")
        if self.institution_location is not None and len(self.institution_location.strip()) < 2:
            raise ValueError("Местоположение учебного учреждения должно быть не менее 2 символов")
        if self.grade is not None and not (1 <= self.grade <= 12):
            raise ValueError("Класс должен быть от 1 до 12")

    def update_profile(
        self,
        full_name: str | None = None,
        school: str | None = None,
        grade: int | None = None,
        institution_location: str | None = None,
        is_captain: bool | None = None,
        dob: dt.date | None = None,
        position: str | None = None,
        military_rank: str | None = None,
        passport_series_number: str | None = None,
        passport_issued_by: str | None = None,
        passport_issued_date: dt.date | None = None,
        military_booklet_number: str | None = None,
        military_personal_number: str | None = None,
    ):
        """Update participant profile."""
        if full_name is not None:
            if len(full_name.strip()) < 2:
                raise ValueError("ФИО должно быть не менее 2 символов")
            self.full_name = full_name

        if school is not None:
            if len(school.strip()) < 2:
                raise ValueError("Название учебного учреждения должно быть не менее 2 символов")
            self.school = school

        if grade is not None:
            if not (1 <= grade <= 12):
                raise ValueError("Класс должен быть от 1 до 12")
            self.grade = grade
        if institution_location is not None:
            if len(institution_location.strip()) < 2:
                raise ValueError("Местоположение учебного учреждения должно быть не менее 2 символов")
            self.institution_location = institution_location
        if is_captain is not None:
            self.is_captain = is_captain
        if dob is not None:
            self.dob = dob
        if position is not None:
            self.position = position or None
        if military_rank is not None:
            self.military_rank = military_rank or None
        if passport_series_number is not None:
            self.passport_series_number = passport_series_number or None
        if passport_issued_by is not None:
            self.passport_issued_by = passport_issued_by or None
        if passport_issued_date is not None:
            self.passport_issued_date = passport_issued_date
        if military_booklet_number is not None:
            self.military_booklet_number = military_booklet_number or None
        if military_personal_number is not None:
            self.military_personal_number = military_personal_number or None

        self.updated_at = datetime.utcnow()
