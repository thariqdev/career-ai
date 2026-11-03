"""Make your existing Career AI data YOUR account (stage 100). Run from backend/:

    .venv/Scripts/python scripts/claim_account.py --email you@example.com

Before accounts, all data belonged to one built-in user (me@career-ai.local) with no
password, so nobody can log into it. This gives that user your email and a password you
type (asked twice, never shown, stored only as a scrypt hash). Nothing is copied, moved
or deleted. It refuses if the email belongs to another account, or if the built-in user
already has a password.

Run `alembic upgrade head` first (after a backup), so the accounts tables exist.
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.exceptions import DomainError  # noqa: E402
from app.core.services import auth_service  # noqa: E402
from database import engine  # noqa: E402


def main(argv: list[str] | None = None, ask=getpass.getpass) -> int:
    parser = argparse.ArgumentParser(description="Claim the built-in user as your account.")
    parser.add_argument("--email", required=True, help="the email you'll log in with")
    parser.add_argument("--name", default=None, help="your name (optional; kept if already saved)")
    args = parser.parse_args(argv)

    password = ask("Choose a password (at least 8 characters): ")
    if password != ask("Type it again: "):
        print("The two passwords don't match. Nothing changed.")
        return 1
    with Session(engine) as db:
        try:
            user = auth_service.claim_built_in_user(db, args.email, password, args.name)
        except DomainError as error:
            print(f"{error} Nothing changed.")
            return 1
        db.commit()
        print(f"Done. Log in as {user.email}: all your existing data is in this account.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
