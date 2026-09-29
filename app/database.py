from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import settings
from app.utils.logging import logger

def get_clean_database_url(raw_url: str) -> str:
    """Normalizes database URLs (e.g. Render's postgres:// to postgresql+psycopg2://)."""
    if not raw_url:
        return "sqlite:///./mail2whatsapp.db"
    url = raw_url.strip()
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


db_url = get_clean_database_url(settings.DATABASE_URL)

connect_args = {}
if db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    engine = create_engine(
        db_url,
        connect_args=connect_args,
    )
else:
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_recycle=300,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI database dependency provider."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initializes tables in database if they do not exist."""
    # Import all models so metadata knows about them
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized successfully.")
