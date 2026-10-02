"""GET /export: download everything Career AI stores for you, as one JSON file.

Read-only (no commit): it only reads through export_service. The Content-Disposition
header makes a browser save it as career-ai-export-YYYY-MM-DD.json when opened directly;
the frontend fetches the JSON and saves it itself.
"""

from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.services import export_service
from app.db.models import User
from app.dependencies import get_current_user, get_db

router = APIRouter(tags=["export"])


@router.get("/export")
def export_my_data(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    filename = f"career-ai-export-{date.today().isoformat()}.json"
    return JSONResponse(
        export_service.export_all(db, user),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
