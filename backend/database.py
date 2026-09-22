import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Load environment variables from the .env file.
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL is None:
    raise ValueError("DATABASE_URL is not set. Please check your .env file.")

# Engine = connection pool + dialect factory.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# SessionLocal = factory for creating Session objects.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all future SQLAlchemy models.
class Base(DeclarativeBase):
    pass



