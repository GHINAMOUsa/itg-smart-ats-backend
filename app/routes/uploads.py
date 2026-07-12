import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status

from app.config import settings
from app.dependencies import require_candidate
from app.models import User
from app.schemas import UploadOut

router = APIRouter(prefix="/api/uploads", tags=["Uploads"])

ALLOWED_RESUME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
ALLOWED_PORTFOLIO_TYPES = ALLOWED_RESUME_TYPES | {"image/png", "image/jpeg"}


def _save_upload(file: UploadFile, subdir: str, allowed_types: set[str]) -> UploadOut:
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type}",
        )

    contents_len = 0
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    target_dir = Path(settings.UPLOAD_DIR) / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    extension = Path(file.filename or "").suffix
    stored_name = f"{uuid.uuid4()}{extension}"
    target_path = target_dir / stored_name

    with open(target_path, "wb") as out_file:
        while chunk := file.file.read(1024 * 1024):
            contents_len += len(chunk)
            if contents_len > max_bytes:
                out_file.close()
                target_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB}MB limit",
                )
            out_file.write(chunk)

    url = f"/uploads/{subdir}/{stored_name}"
    return UploadOut(url=url, filename=file.filename or stored_name)


@router.post("/resume", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
def upload_resume(file: UploadFile = File(...), current_user: User = Depends(require_candidate)):
    """Matches the 'Attach Resume *' file input on the apply form."""
    return _save_upload(file, "resumes", ALLOWED_RESUME_TYPES)


@router.post("/portfolio", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
def upload_portfolio(file: UploadFile = File(...), current_user: User = Depends(require_candidate)):
    """Matches the 'Attach Portfolio' file input on the apply form."""
    return _save_upload(file, "portfolios", ALLOWED_PORTFOLIO_TYPES)
