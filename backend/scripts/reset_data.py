"""Empty every Career AI table, after saving a full backup. Run from backend/:

    .venv/Scripts/python scripts/reset_data.py --yes

1. Writes a "Download my data" backup (export_service, the same JSON "Restore from
   backup" accepts) to backups/backup-<timestamp>.json. If that fails, nothing is deleted.
2. Deletes every row from every table (the schema and alembic_version stay), in one
   transaction, and restarts the id counters on PostgreSQL.

The built-in user (me@career-ai.local) is recreated automatically on the next request.
Refuses to run without --yes, because emptying the database can't be undone (except by
restoring the backup).
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, delete, select, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.services import export_service  # noqa: E402
from app.db.models import User  # noqa: E402
from database import Base, engine as default_engine  # noqa: E402

BACKUP_DIR = Path(__file__).resolve().parent.parent / "backups"


def backup(engine: Engine, backup_dir: Path) -> Path | None:
    """Export every user's data to a timestamped file. Returns None when there's no user."""
    with Session(engine) as db:
        users = list(db.scalars(select(User).order_by(User.id)))
        if not users:
            return None
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = backup_dir / f"backup-{stamp}.json"
        exports = [export_service.export_all(db, user) for user in users]
        # One user (the normal case): the exact "Download my data" format, restorable as is.
        data = exports[0] if len(exports) == 1 else {"users": exports}
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return path


def empty_all_tables(engine: Engine) -> None:
    tables = list(reversed(Base.metadata.sorted_tables))  # children before parents
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            names = ", ".join(t.name for t in tables)
            connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY"))
        else:
            for table in tables:
                connection.execute(delete(table))


def counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {
            t.name: connection.execute(select(text("count(*)")).select_from(t)).scalar()
            for t in Base.metadata.sorted_tables
        }


def main(argv: list[str] | None = None, engine: Engine = default_engine, backup_dir: Path = BACKUP_DIR) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="really empty the database")
    args = parser.parse_args(argv)
    if not args.yes:
        print("Refusing to run without --yes: this empties every table (a backup is saved first).")
        return 2

    path = backup(engine, backup_dir)
    print(f"Backup saved to {path}" if path else "Nothing to back up (no user yet).")
    empty_all_tables(engine)
    left = {name: n for name, n in counts(engine).items() if n}
    print("All tables are empty." if not left else f"Rows left: {left}")
    return 0 if not left else 1


if __name__ == "__main__":
    raise SystemExit(main())
