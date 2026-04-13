from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_current_user, get_db_session
from app.integrations.ocr.providers import OCRParseError, OCRServiceError, OCRNetworkError
from app.models import User
from app.schemas.profile import OCRParseRequest, OCRParseResponse
from app.services.bootstrap import ServiceContainer

router = APIRouter()

# Map OCR error types to HTTP status codes
_OCR_ERROR_STATUS: dict[type, int] = {
    OCRParseError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    OCRServiceError: status.HTTP_502_BAD_GATEWAY,
    OCRNetworkError: status.HTTP_504_GATEWAY_TIMEOUT,
}


@router.post("/parse", response_model=OCRParseResponse)
async def parse_document(
    payload: OCRParseRequest,
    current_user: User = Depends(get_current_user),
    container: ServiceContainer = Depends(get_container),
    db: Session = Depends(get_db_session),
) -> OCRParseResponse:
    # Verify user has access
    if current_user.role not in ["student", "admin", "teacher"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问")

    try:
        if payload.uploaded_file_id:
            result = await container.file_service.parse_uploaded_file(db, payload.uploaded_file_id, payload.document_type)
        elif payload.raw_text:
            result = await container.file_service.ocr_provider.parse_document(
                file_name="manual_input.txt",
                content_bytes=payload.raw_text.encode("utf-8"),
                document_type=payload.document_type,
                raw_text=payload.raw_text,
            )
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请提供 uploaded_file_id 或 raw_text")
        return OCRParseResponse(**result)
    except (OCRParseError, OCRServiceError, OCRNetworkError) as e:
        http_status = _OCR_ERROR_STATUS.get(type(e), status.HTTP_500_INTERNAL_SERVER_ERROR)
        raise HTTPException(
            status_code=http_status,
            detail=e.to_dict(),
        ) from e

