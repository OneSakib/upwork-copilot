from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import models  # noqa: F401  (register tables)
from .db import Base, engine
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with engine.begin() as c:
        c.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_jobs_fts ON jobs USING gin "
            "(to_tsvector('english', coalesce(title,'') || ' ' || coalesce(description,'')))"))
    yield


app = FastAPI(title="Upwork Job Copilot API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/health")
def health():
    return {"ok": True}
