"""Auth-related DTOs."""

import datetime as dt
from dataclasses import dataclass
from uuid import UUID

from ...domain.value_objects import UserRole


@dataclass
class RegisterUserDTO:
    """DTO for user registration."""
    email: str
    password: str
    role: UserRole
    full_name: str | None = None  # For participants
    school: str | None = None  # For participants
    grade: int | None = None  # For participants
    institution_id: UUID | None = None
    institution_location: str | None = None
    is_captain: bool = False
    dob: dt.date | None = None


@dataclass
class LoginUserDTO:
    """DTO for user login."""
    email: str
    password: str


@dataclass
class AuthResponseDTO:
    """DTO for authentication response."""
    access_token: str
    token_type: str = "bearer"
    user_id: UUID | None = None
    email: str | None = None
    role: UserRole | None = None
