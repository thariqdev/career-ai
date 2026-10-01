"""CV endpoints: scan a CV for saved skills (preview), then save the user's confirmed choices.

Two steps on purpose: CV presence is a fact the user supplies (CVSkillPresence), so a
scan only SUGGESTS; nothing is written until the user confirms via PUT /cv/presence.
The CV text is never stored. Neither step touches verification: a CV is a claim, not
proof. Both routes are user-scoped via get_current_user.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.models import CVPresenceBatch, CVPresenceResponse, CVScanResponse
from app.core.services import cv_import_service, cv_presence_service, skill_service
from app.db.models import CVSkillPresence, User
from app.dependencies import get_current_user, get_db

router = APIRouter(prefix="/cv", tags=["cv"])


@router.post("/scan", response_model=CVScanResponse)
def scan_cv(
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CVScanResponse:
    if (file is None) == (text is None):
        raise HTTPException(status_code=422, detail="Send either a CV file or pasted text.")
    if file is not None:
        # Read one byte past the limit, so an oversized file is rejected without
        # reading all of it into memory.
        content = file.file.read(cv_import_service.MAX_CV_BYTES + 1)
        cv_text = cv_import_service.extract_text(file.filename or "", content)
    else:
        cv_text = cv_import_service.check_pasted_text(text)
    return CVScanResponse.from_scan(cv_import_service.scan_cv(db, user, cv_text))


@router.put("/presence", response_model=list[CVPresenceResponse])
def save_cv_presence(
    payload: CVPresenceBatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CVSkillPresence]:
    present_ids = list(dict.fromkeys(payload.present_skill_ids))
    absent_ids = list(dict.fromkeys(payload.absent_skill_ids))
    overlap = set(present_ids) & set(absent_ids)
    if overlap:
        raise HTTPException(
            status_code=422,
            detail=f"Skill ids {sorted(overlap)} can't be both on and off the CV.",
        )

    # Check every skill exists BEFORE writing anything, so a bad id saves nothing.
    skills = {}
    for skill_id in present_ids + absent_ids:
        skill = skill_service.get_skill(db, skill_id)
        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found.")
        skills[skill_id] = skill

    saved = [cv_presence_service.set_cv_presence(db, user, skills[i], True) for i in present_ids]
    saved += [cv_presence_service.set_cv_presence(db, user, skills[i], False) for i in absent_ids]
    db.commit()
    return saved
