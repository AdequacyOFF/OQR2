"""Celery tasks for OCR processing of uploaded scans."""

import logging
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .celery_app import celery_app
from ..ocr import PaddleOCRService
from ..ocr.paddle_ocr import OCRResult
from ..storage import MinIOStorage
from ..database.models import ScanModel, AttemptModel, AnswerSheetModel
from ...config import settings
from ...domain.services import TokenService
from ...domain.value_objects import AttemptStatus

logger = logging.getLogger(__name__)

# Synchronous engine for Celery worker (Celery is sync)
_sync_engine = None
_SessionLocal = None


def _get_sync_url(async_url: str) -> str:
    """Convert async database URL to sync URL for Celery.

    Handles common async driver patterns:
    - postgresql+asyncpg://  -> postgresql+psycopg2://
    - postgresql://          -> postgresql+psycopg2://  (already sync-compatible)
    """
    url = async_url
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg2")
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _get_sync_session() -> Session:
    """Get synchronous DB session for Celery worker."""
    global _sync_engine, _SessionLocal
    if _sync_engine is None:
        sync_url = _get_sync_url(settings.database_url)
        _sync_engine = create_engine(sync_url)
        _SessionLocal = sessionmaker(bind=_sync_engine)
    return _SessionLocal()


@celery_app.task(
    name="olimpqr.process_scan_ocr",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def process_scan_ocr(self, scan_id: str) -> dict:
    """Process an uploaded scan: extract QR, run OCR, update DB.

    Args:
        scan_id: Scan UUID as string

    Returns:
        Dict with OCR results
    """
    logger.info("Processing scan %s", scan_id)
    scan_uuid = UUID(scan_id)
    storage = MinIOStorage()
    ocr_service = PaddleOCRService(use_gpu=settings.ocr_use_gpu)
    token_service = TokenService(settings.hmac_secret_key)

    session = _get_sync_session()
    try:
        # 1. Load scan from DB
        scan_model = session.get(ScanModel, scan_uuid)
        if not scan_model:
            return {"scan_id": scan_id, "status": "error", "message": "Скан не найден"}

        # 2. Download image from MinIO
        image_bytes = storage.download_file(
            bucket=settings.minio_bucket_scans,
            object_name=scan_model.file_path,
        )

        # 3. Extract QR code -> find AnswerSheet/Attempt
        qr_data = ocr_service.extract_qr_from_image(image_bytes)
        attempt_model = None
        is_primary_sheet = True

        if qr_data:
            # New direct token format for Word templates: attempt:<attempt_id>:...
            if qr_data.startswith("attempt:"):
                parts = qr_data.split(":")
                if len(parts) >= 2:
                    try:
                        parsed_attempt_id = UUID(parts[1])
                        attempt_model = session.get(AttemptModel, parsed_attempt_id)
                        # Word template QRs may represent cover/task docs.
                        # Do not auto-apply OCR score for this format to avoid accidental score overwrite.
                        is_primary_sheet = False
                    except ValueError:
                        attempt_model = None
            else:
                # Compute hash of sheet token
                sheet_hash = token_service.hash_token(qr_data)
                answer_sheet_model = (
                    session.query(AnswerSheetModel)
                    .filter(AnswerSheetModel.sheet_token_hash == sheet_hash.value)
                    .first()
                )
                if answer_sheet_model:
                    attempt_model = session.get(AttemptModel, answer_sheet_model.attempt_id)
                    scan_model.answer_sheet_id = answer_sheet_model.id
                    kind_value = (
                        answer_sheet_model.kind.value
                        if hasattr(answer_sheet_model.kind, "value")
                        else str(answer_sheet_model.kind)
                    )
                    is_primary_sheet = kind_value == "primary"
                else:
                    # Backward compatibility for old sheets.
                    attempt_model = (
                        session.query(AttemptModel)
                        .filter(AttemptModel.sheet_token_hash == sheet_hash.value)
                        .first()
                    )

            if attempt_model and scan_model.attempt_id is None:
                scan_model.attempt_id = attempt_model.id

        # 4. Run OCR on score field
        ocr_result: OCRResult = ocr_service.extract_score_from_image(
            image_bytes=image_bytes,
            score_field_x=settings.ocr_score_field_x,
            score_field_y=settings.ocr_score_field_y,
            score_field_width=settings.ocr_score_field_width,
            score_field_height=settings.ocr_score_field_height,
        )

        # 5. Update scan with OCR results
        scan_model.ocr_score = ocr_result.score
        scan_model.ocr_confidence = ocr_result.confidence
        scan_model.ocr_raw_text = ocr_result.raw_text

        # 6. If confidence is high enough and attempt was found, auto-apply score
        if (
            attempt_model
            and is_primary_sheet
            and ocr_result.score is not None
            and ocr_result.confidence >= settings.ocr_confidence_threshold
        ):
            attempt_model.score_total = ocr_result.score
            attempt_model.confidence = ocr_result.confidence
            attempt_model.status = AttemptStatus.SCORED
            logger.info(
                "Auto-applied score %d (confidence %.2f) for attempt %s",
                ocr_result.score,
                ocr_result.confidence,
                attempt_model.id,
            )
        elif attempt_model:
            # Low confidence → mark as SCANNED, needs manual verification
            if attempt_model.status == AttemptStatus.PRINTED:
                attempt_model.status = AttemptStatus.SCANNED
            logger.info(
                "Low confidence (%.2f) for attempt %s – needs manual verification",
                ocr_result.confidence,
                attempt_model.id,
            )

        session.commit()

        return {
            "scan_id": scan_id,
            "status": "completed",
            "ocr_score": ocr_result.score,
            "ocr_confidence": ocr_result.confidence,
            "ocr_raw_text": ocr_result.raw_text,
            "qr_found": qr_data is not None,
            "attempt_linked": attempt_model is not None,
            "auto_applied": (
                attempt_model is not None
                and is_primary_sheet
                and ocr_result.score is not None
                and ocr_result.confidence >= settings.ocr_confidence_threshold
            ),
        }

    except Exception as exc:
        session.rollback()
        logger.error("OCR processing failed for scan %s: %s", scan_id, exc, exc_info=True)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {"scan_id": scan_id, "status": "failed", "message": str(exc)}
    finally:
        session.close()
