"""Restore a "Download my data" file into an empty app (see import_service).

POST /import/preview reads the file and reports what it holds and any problems; it never
writes. POST /import checks everything again and restores it in one transaction: 422 for
a bad file, 409 if the app isn't empty, and nothing is saved in either case.
"""

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.services import import_service
from app.db.models import User
from app.demo import forbid_in_demo
from app.dependencies import get_current_user, get_db

# Switched off in the public demo (stage 94): visitors must not replace the demo data.
router = APIRouter(prefix="/import", tags=["import"], dependencies=[Depends(forbid_in_demo)])


class ImportPreviewResponse(BaseModel):
    counts: dict[str, int]
    problems: list[str]
    app_empty: bool


class ImportResultResponse(BaseModel):
    counts: dict[str, int]


def _read(file: UploadFile) -> bytes:
    # One byte past the limit, so an oversized file is refused without reading all of it.
    return file.file.read(import_service.MAX_IMPORT_BYTES + 1)


@router.post("/preview", response_model=ImportPreviewResponse)
def preview_import(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportPreviewResponse:
    result = import_service.preview(db, user, _read(file))
    return ImportPreviewResponse(counts=result.counts, problems=result.problems, app_empty=result.app_empty)


@router.post("", response_model=ImportResultResponse)
def restore_import(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportResultResponse:
    counts = import_service.restore(db, user, _read(file))
    db.commit()
    return ImportResultResponse(counts=counts)
