from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AuthSession(Base):
    """One logged-in browser (stage 97: accounts).

    The browser holds a long random token in an HttpOnly cookie; only its SHA-256 is
    stored here, so a leaked database can't be used to log in. Logging out deletes the
    row; an expired row is treated as logged out (and removed when seen).
    """

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
