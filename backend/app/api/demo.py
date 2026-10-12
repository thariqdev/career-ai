"""GET /demo/status and POST /demo/reset: the public portfolio demo (stage 94, app/demo.py)."""

import hmac
import os

from fastapi import APIRouter, Header, HTTPException

from app import demo
from database import SessionLocal, engine

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/status")
def demo_status() -> dict[str, bool]:
    return {"demo": demo.demo_mode()}


@router.post("/reset")
def demo_reset(x_demo_token: str | None = Header(default=None)) -> dict:
    """Empty the demo database and seed it again. Demo mode only, and only with the secret
    token (DEMO_RESET_TOKEN), which the daily GitHub Action sends."""
    if not demo.demo_mode():
        raise HTTPException(status_code=404, detail="Not found.")
    expected = os.getenv("DEMO_RESET_TOKEN") or ""
    if not expected:
        raise HTTPException(status_code=503, detail="DEMO_RESET_TOKEN isn't configured.")
    if not x_demo_token or not hmac.compare_digest(x_demo_token, expected):
        raise HTTPException(status_code=403, detail="Wrong demo token.")
    return {"reset": True, **demo.reset(engine, SessionLocal)}
