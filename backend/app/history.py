"""Everything the agent 'remembers': win-rate stats, similar past jobs, and past proposals + lessons."""
import re
from collections import Counter

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .models import Job, Proposal

STOP = set("""a an the and or for to of in on with we you your our is are be will need needs looking want seeking expert
experienced skilled freelancer job work project help please must have has this that from can who strong good great ideal
candidate someone person team""".split())
APPLIED = ("applied", "interviewing", "hired", "rejected", "no_response")


def keywords(txt: str, n: int = 12) -> list[str]:
    words = [re.sub(r"[^a-z0-9]", "", w) for w in re.findall(r"[A-Za-z][A-Za-z0-9+#.]{2,}", txt.lower())]
    c = Counter(w for w in words if len(w) > 2 and w not in STOP)
    return [w for w, _ in c.most_common(n)]


def stats(db: Session) -> dict:
    rows = dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    applied = sum(v for k, v in rows.items() if k in APPLIED)
    hired = rows.get("hired", 0)
    replies = hired + rows.get("interviewing", 0)
    return {
        "analyzed_total": sum(rows.values()), "applied": applied, "hired": hired,
        "interviews_or_hires": replies, "rejected": rows.get("rejected", 0), "no_response": rows.get("no_response", 0),
        "win_rate_pct": round(100 * hired / applied) if applied else None,
        "reply_rate_pct": round(100 * replies / applied) if applied else None,
    }


def similar_jobs(db: Session, job: Job, limit: int = 5, only_applied: bool = True) -> list[Job]:
    kws = keywords(f"{job.title or ''} {job.title or ''} {job.title or ''} {(job.description or '')[:1500]}")
    if not kws:
        return []
    status_clause = "AND j.status IN ('applied','interviewing','hired','rejected','no_response')" if only_applied else ""
    sql = text(f"""
        SELECT j.id FROM jobs j, to_tsquery('english', :q) q
        WHERE j.id <> :jid {status_clause}
          AND to_tsvector('english', coalesce(j.title,'') || ' ' || coalesce(j.description,'')) @@ q
        ORDER BY ts_rank(to_tsvector('english', coalesce(j.title,'') || ' ' || coalesce(j.description,'')), q) DESC
        LIMIT :lim""")
    ids = [r[0] for r in db.execute(sql, {"q": " | ".join(kws), "jid": job.id or 0, "lim": limit}).all()]
    if not ids:
        return []
    jobs = {j.id: j for j in db.scalars(select(Job).where(Job.id.in_(ids)))}
    return [jobs[i] for i in ids if i in jobs]


def _short(s: str | None, n: int) -> str:
    return (s or "")[:n]


def proposal_examples(db: Session, job: Job) -> dict:
    """Context for the proposal writer: earlier versions for THIS job, winners and lessons from similar jobs."""
    same = [{
        "version": p.version, "hook": p.hook, "outcome": p.outcome, "lesson": p.lesson, "text": _short(p.text, 1500),
    } for p in job.proposals]
    winning, lessons = [], []
    for sj in similar_jobs(db, job, limit=8):
        for p in sj.proposals:
            if p.outcome == "hired" and len(winning) < 2:
                winning.append({"job_title": sj.title, "hook": p.hook, "text": _short(p.text, 1500), "lesson": p.lesson})
            elif p.outcome in ("rejected", "no_response") and p.lesson and len(lessons) < 3:
                lessons.append({"job_title": sj.title, "outcome": p.outcome, "lesson": p.lesson})
    return {"same_job_versions": same, "winning_examples": winning, "lessons_from_similar_losses": lessons}


def history_brief(db: Session, job: Job) -> dict:
    sim = similar_jobs(db, job)
    return {
        "stats": stats(db),
        "similar": [{"id": j.id, "title": j.title, "status": j.status, "verdict": j.verdict} for j in sim],
    }
