import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from langchain_anthropic import ChatAnthropic
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import history as hist
from .agents import graph as agent
from .agents.prompts import LESSON_SYSTEM
from .config import settings
from .db import SessionLocal, get_db
from .models import Job, Proposal
from .parser import parse_job
from .schemas import AnalyzeRequest, OutcomeRequest, ProposalRequest


def require_token(x_api_token: str = Header(default="")):
    if not secrets.compare_digest(x_api_token, settings.api_token):
        raise HTTPException(401, "Bad or missing X-API-Token")


def anthropic_key() -> str:
    return settings.anthropic_api_key


router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


def _run(db: Session, state: dict, api_key: str) -> dict:
    try:
        return agent.run(db, state)
    except Exception as e:
        msg = str(e).replace(api_key, "***")[:300]
        raise HTTPException(502, f"AI call failed ({type(e).__name__}): {msg}")


def _proposal_dict(p: Proposal) -> dict:
    return {"id": p.id, "version": p.version, "hook": p.hook, "text": p.text, "answers": p.answers,
            "meta": p.meta, "outcome": p.outcome, "lesson": p.lesson, "created_at": p.created_at.isoformat()}


def _payload(db: Session, job: Job) -> dict:
    h = hist.history_brief(db, job)
    return {
        "job_id": job.id, "title": job.title, "status": job.status, "parsed": job.parsed, "rules": job.rules,
        "analysis": job.analysis, "research": job.research, "stats": h["stats"], "similar": h["similar"],
        "proposals": [_proposal_dict(p) for p in job.proposals],
    }


def _upsert(db: Session, scraped: dict, parsed: dict) -> Job:
    uid = parsed.get("upwork_id")
    job = db.scalar(select(Job).where(Job.upwork_id == uid)) if uid else None
    if not job:
        job = db.scalar(select(Job).where(Job.url == scraped["url"]))
    if not job:
        job = Job(upwork_id=uid, url=scraped["url"], status="analyzed")
        db.add(job)
    job.title = scraped.get("title") or job.title
    job.description = scraped.get("description") or scraped.get("raw_text", "")[:8000]
    job.scraped, job.parsed = scraped, parsed
    db.commit()
    return job


@router.get("/ping")
def ping(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"ok": True}


@router.post("/analyze")
def analyze(req: AnalyzeRequest, db: Session = Depends(get_db), api_key: str = Depends(anthropic_key)):
    scraped = req.job.model_dump()
    parsed = parse_job(scraped)
    job = _upsert(db, scraped, parsed)
    final = _run(db, {"mode": "analyze", "job_id": job.id, "job": scraped, "parsed": parsed,
                      "profile": req.profile.model_dump(), "api_key": api_key,
                      "deep_research": req.deep_research}, api_key)
    job.rules, job.analysis, job.research = final["rules"], final["analysis"], final.get("research")
    job.verdict, job.overall = final["analysis"]["verdict"], final["analysis"]["overall"]
    db.commit()
    return _payload(db, job)


@router.post("/jobs/{job_id}/proposal")
def make_proposal(job_id: int, req: ProposalRequest, db: Session = Depends(get_db), api_key: str = Depends(anthropic_key)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    final = _run(db, {"mode": "proposal", "job_id": job.id, "job": job.scraped, "parsed": job.parsed,
                      "profile": req.profile.model_dump(), "api_key": api_key, "deep_research": req.deep_research,
                      "research": job.research or "", "analysis": job.analysis, "rules": job.rules,
                      "extra_instructions": req.extra_instructions}, api_key)
    out = final["proposal"]
    prop = Proposal(job_id=job.id, version=len(job.proposals) + 1, hook=out["hook_used"], text=out["cover_letter"],
                    answers=out["screening_answers"],
                    meta={"suggested_bid": out["suggested_bid"], "attachments": out["attachments_to_mention"],
                          "what_changed": out["what_changed"], "quality_issues": final.get("issues", [])})
    db.add(prop)
    db.commit()
    return _proposal_dict(prop)


@router.post("/jobs/{job_id}/outcome")
def set_outcome(job_id: int, req: OutcomeRequest, bg: BackgroundTasks, db: Session = Depends(get_db),
                api_key: str = Depends(anthropic_key)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.status = req.status
    if req.notes:
        job.notes = req.notes
    if req.connects_spent is not None:
        job.connects_spent = req.connects_spent
    if req.status == "applied" and not job.applied_at:
        job.applied_at = datetime.now(timezone.utc)
    prop = job.proposals[-1] if job.proposals else None
    if prop and req.status in ("interviewing", "hired", "rejected", "no_response"):
        prop.outcome = req.status
        db.commit()
        if req.status in ("hired", "rejected", "no_response"):
            bg.add_task(_write_lesson, prop.id, api_key, req.notes)
    else:
        db.commit()
    return {"ok": True, "status": job.status}


def _write_lesson(proposal_id: int, api_key: str, notes: str):
    db = SessionLocal()
    try:
        p = db.get(Proposal, proposal_id)
        job = p.job
        llm = ChatAnthropic(model=settings.anthropic_model, api_key=api_key, max_tokens=500, timeout=60)
        msg = llm.invoke([("system", LESSON_SYSTEM), ("user",
            f"JOB: {job.title}\nCLIENT FACTS: {job.parsed}\nPROPOSAL (v{p.version}, hook: {p.hook}):\n{p.text}\n"
            f"OUTCOME: {p.outcome}\nFREELANCER NOTES: {notes or 'none'}")])
        p.lesson = agent._text(msg)[:1200]
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


@router.get("/jobs")
def list_jobs(status: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    q = select(Job).order_by(Job.updated_at.desc()).limit(min(limit, 200))
    if status:
        q = q.where(Job.status == status)
    return [{"id": j.id, "title": j.title, "url": j.url, "status": j.status, "verdict": j.verdict, "overall": j.overall,
             "updated_at": j.updated_at.isoformat()} for j in db.scalars(q)]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return _payload(db, job)


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    return hist.stats(db)
