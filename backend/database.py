import os
import ssl
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Load environment variables from the .env file.
load_dotenv()


def normalize_database_url(url: str, force_ssl: bool = False) -> tuple[str, dict]:
    """(SQLAlchemy URL, connect_args) from a URL as hosting services print it.

    Hosted Postgres (Neon, Render...) gives `postgres://...?sslmode=require&channel_binding=...`.
    The pg8000 driver needs the `postgresql+pg8000://` scheme and takes SSL as an SSL context,
    not as query parameters, so those are translated here (stage 94). Other URLs (local
    `postgresql+pg8000://`, `sqlite://`) pass through unchanged.
    """
    parts = urlsplit(url)
    if not parts.scheme.startswith("postgres"):
        return url, {}  # sqlite and others: untouched (rebuilding would mangle "sqlite:///")
    scheme = "postgresql+pg8000" if parts.scheme in ("postgres", "postgresql") else parts.scheme
    use_ssl = force_ssl
    kept = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "sslmode":
            use_ssl = use_ssl or value not in ("disable", "allow", "prefer")
        elif key == "channel_binding":
            continue  # a libpq option pg8000 doesn't take
        else:
            kept.append((key, value))
    connect_args = {"ssl_context": ssl.create_default_context()} if use_ssl else {}
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment)), connect_args


_RAW_URL = os.getenv("DATABASE_URL")

if _RAW_URL is None:
    raise ValueError("DATABASE_URL is not set. Please check your .env file.")

DATABASE_URL, CONNECT_ARGS = normalize_database_url(
    _RAW_URL, force_ssl=(os.getenv("DATABASE_SSL") or "").lower() in ("1", "true", "require")
)

# Engine = connection pool + dialect factory.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=CONNECT_ARGS)

# SessionLocal = factory for creating Session objects.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all future SQLAlchemy models.
class Base(DeclarativeBase):
    pass
