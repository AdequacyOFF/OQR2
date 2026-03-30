"""Scanner API endpoints."""

from typing import Annotated, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ....infrastructure.database import get_db
from ....infrastructure.repositories import (
    ScanRepositoryImpl,
    AttemptRepositoryImpl,
    AuditLogRepositoryImpl,
    AnswerSheetRepositoryImpl,
)
from ....infrastructure.storage import MinIOStorage
from ....infrastructure.tasks.ocr_tasks import process_scan_ocr
from ....domain.entities import Scan, AuditLog
from ....domain.value_objects import UserRole, AttemptStatus
from ....domain.entities import User
from ...schemas.scan_schemas import (
    ScanUploadResponse,
    ScanResponse,
    ScanListResponse,
    VerifyScoreRequest,
    VerifyScoreResponse,
    ApplyScoreRequest,
    AttemptResponse,
)
from ...dependencies import require_role
from ....config import settings

router = APIRouter()


@router.post("/upload", response_model=ScanUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_scan(
    file: UploadFile = File(..., description="Scan image (PNG, JPEG, or PDF)"),
    attempt_id: Optional[UUID] = None,
    current_user: User = Depends(require_role(UserRole.SCANNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Upload a scan image for OCR processing.

    The scan is stored in MinIO and a Celery task is dispatched for OCR.
    If ``attempt_id`` is provided it is linked immediately; otherwise the
    Celery worker will try to link via QR extraction.
    """
    # Validate file type
    allowed = {"image/png", "image/jpeg", "image/jpg", "application/pdf"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail=f"Неподдерживаемый тип файла: {file.content_type}")

    # Read file with size limit
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    file_data = await file.read()
    if len(file_data) == 0:
        raise HTTPException(status_code=400, detail="Пустой файл")
    if len(file_data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Файл слишком большой. Максимальный размер 50МБ")

    # Upload to MinIO
    scan_id = uuid4()
    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "png"
    object_name = f"scans/{scan_id}.{ext}"

    storage = MinIOStorage()
    storage.upload_file(
        bucket=settings.minio_bucket_scans,
        object_name=object_name,
        data=file_data,
        content_type=file.content_type or "image/png",
    )

    # Create Scan entity (attempt_id can be None - will be linked via QR by Celery worker)
    scan = Scan(
        id=scan_id,
        attempt_id=attempt_id,
        file_path=object_name,
        uploaded_by=current_user.id,
    )

    scan_repo = ScanRepositoryImpl(db)
    await scan_repo.create(scan)

    # Dispatch OCR task
    task = process_scan_ocr.delay(str(scan_id))

    return ScanUploadResponse(scan_id=scan_id, task_id=task.id)


@router.get("", response_model=ScanListResponse)
async def list_scans(
    skip: int = 0,
    limit: int = 50,
    unverified_only: bool = False,
    current_user: User = Depends(require_role(UserRole.SCANNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """List uploaded scans with optional filter for unverified."""
    scan_repo = ScanRepositoryImpl(db)

    if unverified_only:
        scans = await scan_repo.get_unverified(skip=skip, limit=limit)
    else:
        scans = await scan_repo.get_all(skip=skip, limit=limit)

    items = [
        ScanResponse(
            id=s.id,
            attempt_id=s.attempt_id,
            answer_sheet_id=s.answer_sheet_id,
            file_path=s.file_path,
            ocr_score=s.ocr_score,
            ocr_confidence=s.ocr_confidence,
            ocr_raw_text=s.ocr_raw_text,
            verified_by=s.verified_by,
            uploaded_by=s.uploaded_by,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in scans
    ]

    return ScanListResponse(items=items, total=len(items))


@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(
    scan_id: UUID,
    current_user: User = Depends(require_role(UserRole.SCANNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Get scan details including OCR results."""
    scan_repo = ScanRepositoryImpl(db)
    scan = await scan_repo.get_by_id(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Скан не найден")

    return ScanResponse(
        id=scan.id,
        attempt_id=scan.attempt_id,
        answer_sheet_id=scan.answer_sheet_id,
        file_path=scan.file_path,
        ocr_score=scan.ocr_score,
        ocr_confidence=scan.ocr_confidence,
        ocr_raw_text=scan.ocr_raw_text,
        verified_by=scan.verified_by,
        uploaded_by=scan.uploaded_by,
        created_at=scan.created_at,
        updated_at=scan.updated_at,
    )


@router.get("/{scan_id}/image")
async def get_scan_image(
    scan_id: UUID,
    current_user: User = Depends(require_role(UserRole.SCANNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Download the scan image file."""
    scan_repo = ScanRepositoryImpl(db)
    scan = await scan_repo.get_by_id(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Скан не найден")

    storage = MinIOStorage()
    try:
        file_bytes = storage.download_file(
            bucket=settings.minio_bucket_scans,
            object_name=scan.file_path,
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Файл скана не найден в хранилище")

    ext = scan.file_path.rsplit(".", 1)[-1].lower() if "." in scan.file_path else "png"
    content_type_map = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "pdf": "application/pdf",
    }
    content_type = content_type_map.get(ext, "application/octet-stream")

    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="scan-{scan_id}.{ext}"'},
    )


@router.post("/{scan_id}/verify", response_model=VerifyScoreResponse)
async def verify_scan_score(
    scan_id: UUID,
    body: VerifyScoreRequest,
    request: Request,
    current_user: User = Depends(require_role(UserRole.SCANNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Manually verify / correct OCR score and apply it to the attempt."""
    scan_repo = ScanRepositoryImpl(db)
    attempt_repo = AttemptRepositoryImpl(db)
    audit_repo = AuditLogRepositoryImpl(db)

    scan = await scan_repo.get_by_id(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Скан не найден")

    # Check if scan has linked attempt
    if not scan.attempt_id:
        raise HTTPException(status_code=400, detail="Скан не привязан к попытке. QR-код ещё не распознан.")

    # Verify and correct scan
    scan.verify(verified_by=current_user.id, corrected_score=body.corrected_score)
    await scan_repo.update(scan)

    # Extra sheets must not affect final score.
    if scan.answer_sheet_id:
        answer_sheet_repo = AnswerSheetRepositoryImpl(db)
        answer_sheet = await answer_sheet_repo.get_by_id(scan.answer_sheet_id)
        if answer_sheet and answer_sheet.kind.value == "extra":
            return VerifyScoreResponse(
                scan_id=scan.id,
                attempt_id=scan.attempt_id,
                score=body.corrected_score,
                verified_by=current_user.id,
            )

    # Apply score to attempt
    attempt = await attempt_repo.get_by_id(scan.attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Попытка не найдена")

    attempt.apply_score(score=body.corrected_score, confidence=None)
    await attempt_repo.update(attempt)

    # Audit log
    audit = AuditLog.create_log(
        entity_type="attempt",
        entity_id=attempt.id,
        action="score_verified",
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        corrected_score=body.corrected_score,
        scan_id=str(scan_id),
    )
    await audit_repo.create(audit)

    return VerifyScoreResponse(
        scan_id=scan.id,
        attempt_id=attempt.id,
        score=body.corrected_score,
        verified_by=current_user.id,
    )


@router.post("/attempts/{attempt_id}/apply-score", response_model=AttemptResponse)
async def apply_score(
    attempt_id: UUID,
    body: ApplyScoreRequest,
    request: Request,
    current_user: User = Depends(require_role(UserRole.SCANNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Directly apply or override the score for an attempt."""
    attempt_repo = AttemptRepositoryImpl(db)
    audit_repo = AuditLogRepositoryImpl(db)

    attempt = await attempt_repo.get_by_id(attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Попытка не найдена")

    try:
        attempt.apply_score(score=body.score, confidence=None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await attempt_repo.update(attempt)

    # Audit
    audit = AuditLog.create_log(
        entity_type="attempt",
        entity_id=attempt.id,
        action="score_applied",
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        score=body.score,
    )
    await audit_repo.create(audit)

    return AttemptResponse(
        id=attempt.id,
        registration_id=attempt.registration_id,
        variant_number=attempt.variant_number,
        status=attempt.status.value,
        score_total=attempt.score_total,
        confidence=attempt.confidence,
        pdf_file_path=attempt.pdf_file_path,
        created_at=attempt.created_at,
        updated_at=attempt.updated_at,
    )
