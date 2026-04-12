"""SQLAlchemy ORM models."""

from .user import UserModel
from .participant import ParticipantModel
from .competition import CompetitionModel
from .registration import RegistrationModel
from .entry_token import EntryTokenModel
from .attempt import AttemptModel
from .scan import ScanModel
from .audit_log import AuditLogModel
from .institution import InstitutionModel
from .room import RoomModel
from .seat_assignment import SeatAssignmentModel
from .document import DocumentModel
from .participant_event import ParticipantEventModel
from .answer_sheet import AnswerSheetModel
from .badge_photo import BadgePhotoModel
from .badge_template import BadgeTemplateModel
from .user_competition_access import UserCompetitionAccessModel
from .tour_time import TourTimeModel
from .staff_badge import StaffBadgeModel

__all__ = [
    "UserModel",
    "ParticipantModel",
    "CompetitionModel",
    "RegistrationModel",
    "EntryTokenModel",
    "AttemptModel",
    "ScanModel",
    "AuditLogModel",
    "InstitutionModel",
    "RoomModel",
    "SeatAssignmentModel",
    "DocumentModel",
    "ParticipantEventModel",
    "AnswerSheetModel",
    "BadgePhotoModel",
    "BadgeTemplateModel",
    "UserCompetitionAccessModel",
    "TourTimeModel",
    "StaffBadgeModel",
]
