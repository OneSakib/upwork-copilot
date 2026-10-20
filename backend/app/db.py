from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

url = make_url(settings.database_url)
connect_args = {}
if "sslmode" not in url.query:
    connect_args["sslmode"] = "require"  # Supabase only accepts TLS connections
if url.port == 6543:
    # Supabase transaction pooler (pgbouncer) does not support prepared statements
    connect_args["prepare_threshold"] = None

engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=300,
                       connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
