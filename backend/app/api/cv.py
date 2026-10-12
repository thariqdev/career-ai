"""CV endpoints: scan a CV (preview), save confirmed choices, and list combined CV status.

Two steps on purpose: CV presence is a fact the user supplies (CVSkillPresence), so a
scan only SUGGESTS; nothing is written until the user confirms via PUT /cv/presence.
The CV text is never stored. Neither step touches verification: a CV is a claim, not
proof. POST /cv/add-all is the one-click version: it saves every skill the CV mentions,
marks them on the CV and claims them as PROVISIONAL (never verified). POST /cv/replace
starts fresh: it removes the current person's data first (stage 95). All routes are
user-scoped via get_current_user.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.models import (
    CVAdoptResponse,
    CVPresenceBatch,
    CVPresenceResponse,
    CVReplaceResponse,
    CVScanResponse,
    CVStatusResponse,
)
from app.core.services import (
    cv_adopt_service,
    cv_import_service,
    cv_presence_service,
    cv_replace_service,
    cv_service,
    skill_service,
)
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
    return CVScanResponse.from_scan(cv_import_service.scan_cv(db, user, _cv_text(file, text)))


@router.post("/add-all", response_model=CVAdoptResponse)
def add_all_cv_skills(
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> cv_adopt_service.AdoptResult:
    """Save every skill the CV mentions, mark it on the CV, claim it as provisional."""
    result = cv_adopt_service.add_all_from_cv(db, user, _cv_text(file, text))
    db.commit()
    return result


@router.post("/replace", response_model=CVReplaceResponse)
def replace_with_cv(
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> cv_replace_service.ReplaceResult:
    """Start fresh: remove this person's data, then add the new CV's skills (provisional)
    and return its projects, work and education as drafts. The CV is read before anything
    is removed, so an unreadable file changes nothing."""
    from app.rag import note_cache

    cv_text = _cv_text(file, text)
    result = cv_replace_service.replace_with_cv(db, user, cv_text)
    db.commit()
    note_cache.clear()  # the assistant's notes described the previous person
    return result


def _cv_text(file: UploadFile | None, text: str | None) -> str:
    """The CV as text, from an upload or pasted text (exactly one). Never stored."""
    if (file is None) == (text is None):
        raise HTTPException(status_code=422, detail="Send either a CV file or pasted text.")
    if file is not None:
        # Read one byte past the limit, so an oversized file is rejected without
        # reading all of it into memory.
        content = file.file.read(cv_import_service.MAX_CV_BYTES + 1)
        return cv_import_service.extract_text(file.filename or "", content)
    return cv_import_service.check_pasted_text(text)


@router.get("/status", response_model=list[CVStatusResponse])
def list_cv_status(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[CVStatusResponse]:
    """Combined knowledge + CV status for every skill you've claimed or marked on your CV.

    One request instead of one per skill. A skill with neither isn't listed: callers
    treat it as "no claim, not on CV". Read-only, same as GET /skills/{id}/cv-status.
    """
    return [
        CVStatusResponse.from_combined_status(combined)
        for combined in cv_service.combined_status_for_all(db, user)
    ]


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
