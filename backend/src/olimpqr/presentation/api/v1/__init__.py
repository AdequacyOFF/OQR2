"""API v1 routers."""

from fastapi import APIRouter
from .auth import router as auth_router
from .competitions import router as competitions_router
from .registrations import router as registrations_router
from .admission import router as admission_router
from .scans import router as scans_router
from .admin import router as admin_router
from .results import router as results_router
from .profiles import router as profiles_router
from .institutions import router as institutions_router
from .rooms import router as rooms_router
from .invigilator import router as invigilator_router
from .documents import router as documents_router
from .staff_badges import router as staff_badges_router

api_router = APIRouter()

# Include routers
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(competitions_router, prefix="/competitions", tags=["Competitions"])
api_router.include_router(registrations_router, prefix="/registrations", tags=["Registrations"])
api_router.include_router(admission_router, prefix="/admission", tags=["Admission"])
api_router.include_router(scans_router, prefix="/scans", tags=["Scans"])
api_router.include_router(admin_router, prefix="/admin", tags=["Admin"])
api_router.include_router(results_router, prefix="/results", tags=["Results"])
api_router.include_router(profiles_router, prefix="/profile", tags=["Profile"])
api_router.include_router(institutions_router, prefix="/institutions", tags=["Institutions"])
api_router.include_router(rooms_router, prefix="/rooms", tags=["Rooms"])
api_router.include_router(invigilator_router, prefix="/invigilator", tags=["Invigilator"])
api_router.include_router(documents_router, prefix="/documents", tags=["Documents"])
api_router.include_router(staff_badges_router, prefix="/admin/staff-badges", tags=["Staff Badges"])

__all__ = ["api_router"]
