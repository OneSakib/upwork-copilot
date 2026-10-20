"""LangGraph agent.

analyze : score_rules -> load_history -> research(web search) -> analyst
proposal: load_history -> research(skipped if already done) -> writer -> critic -> (writer again if issues, max 3 drafts)
"""
import re
from typing import TypedDict

from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from .. import history as hist
from ..config import settings
from ..models import Job
from ..schemas import Analysis, ProposalOut
from ..scoring import evaluate
from . import prompts


class State(TypedDict, total=False):
    mode: str
    job_id: int
    job: dict
    parsed: dict
    profile: dict
    api_key: str
    deep_research: bool
    rules: dict
    history: dict
    examples: dict
    research: str
    analysis: dict
    proposal: dict
    issues: list
    attempts: int
    extra_instructions: str


def llm(state: State, max_tokens: int = 4096) -> ChatAnthropic:
    return ChatAnthropic(model=settings.anthropic_model, api_key=state["api_key"], max_tokens=max_tokens, timeout=120, max_retries=2)


def _text(msg) -> str:
    c = msg.content
    if isinstance(c, str):
        return c
    return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")


def check_proposal(p: dict, profile: dict) -> list[str]:
    issues = []
    text = p["cover_letter"]
    low = (text + " " + " ".join(a["answer"] for a in p.get("screening_answers", []))).lower()
    for w in profile.get("banned_words") or []:
        pat = r"[-\s]".join(re.escape(x) for x in re.split(r"[-\s]+", w.lower().strip()) if x)
        if pat and re.search(rf"\b{pat}", low):
            issues.append(f"Contains banned word '{w}'. Remove it.")
    n = len(text)
    if n < 500:
        issues.append(f"Too short ({n} chars). Aim for 900-1400.")
    elif n > 1800:
        issues.append(f"Too long ({n} chars). Aim for 900-1400.")
    first = text.strip().splitlines()[0].lower() if text.strip() else ""
    if re.search(r"i am an expert|i'm an expert|i understand", first):
        issues.append("First line must not say 'expert' or 'I understand'.")
    bullets = [l for l in text.splitlines() if re.match(r"^\s*(✅|✔️|✔|•|-|\*|\d+[.)])\s*", l)]
    if len(bullets) < 3:
        issues.append("Needs 4 checkmark bullets (✅) describing how the job will be done.")
    if "?" not in text:
        issues.append("Needs one short question about the job.")
    links = profile.get("case_study_links") or []
    if links and not any(u in text for u in links) and "case study" not in low:
        issues.append("Mention the attached case study and include its link.")
    if re.search(r"written (by a human|manually|by hand)|took me \d+", low):
        issues.append("Remove claims that the letter was handwritten / human-written / took X minutes.")
    return issues


def build_graph(db: Session):
    def score_rules(s: State):
        return {"rules": evaluate(s["parsed"], s["profile"])}

    def load_history(s: State):
        job = db.get(Job, s["job_id"])
        out = {"history": hist.history_brief(db, job)}
        if s["mode"] == "proposal":
            out["examples"] = hist.proposal_examples(db, job)
        return out

    def research(s: State):
        if not s.get("deep_research") or s.get("research"):
            return {}
        try:
            tool = {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}
            msg = llm(s, 1500).bind_tools([tool]).invoke([("system", prompts.RESEARCH_SYSTEM), ("user", prompts.job_brief(s))])
            return {"research": _text(msg)[:3000]}
        except Exception as e:  # research is optional; never block the analysis on it
            return {"research": f"(web research unavailable: {type(e).__name__})"}

    def analyst(s: State):
        out = llm(s).with_structured_output(Analysis).invoke(
            [("system", prompts.ANALYST_SYSTEM), ("user", prompts.analyst_user(s))])
        a = out.model_dump()
        for k in ("confidence", "profile_fit", "response_chance", "win_chance"):
            a[k] = max(0, min(100, int(a[k])))
        r, reason = s["rules"], None
        if r["hard_stop"]:
            a["verdict"], reason = "SKIP", r["hard_stop_reason"]
        elif r["fake_risk"] >= 70:
            a["verdict"], reason = "SKIP", f"Fake-client risk is {r['fake_risk']}/100."
        elif a["verdict"] == "APPLY" and r["rule_score"] < 40:
            a["verdict"], reason = "MAYBE", f"Downgraded: rule score is only {r['rule_score']}/100."
        a["verdict_override"] = reason
        a["overall"] = round(0.4 * r["rule_score"] + 0.3 * a["profile_fit"] + 0.3 * a["response_chance"])
        return {"analysis": a}

    def writer(s: State):
        out = llm(s, 3500).with_structured_output(ProposalOut).invoke(
            [("system", prompts.writer_system(s["profile"])), ("user", prompts.writer_user(s))])
        return {"proposal": out.model_dump(), "attempts": s.get("attempts", 0) + 1}

    def critic(s: State):
        return {"issues": check_proposal(s["proposal"], s["profile"])}

    g = StateGraph(State)
    for name, fn in [("score_rules", score_rules), ("load_history", load_history), ("research", research),
                     ("analyst", analyst), ("writer", writer), ("critic", critic)]:
        g.add_node(name, fn)
    g.add_conditional_edges(START, lambda s: "score_rules" if s["mode"] == "analyze" else "load_history")
    g.add_edge("score_rules", "load_history")
    g.add_edge("load_history", "research")
    g.add_conditional_edges("research", lambda s: "analyst" if s["mode"] == "analyze" else "writer")
    g.add_edge("analyst", END)
    g.add_edge("writer", "critic")
    g.add_conditional_edges("critic", lambda s: "writer" if s["issues"] and s.get("attempts", 0) < 3 else END)
    return g.compile()


def run(db: Session, state: State) -> State:
    return build_graph(db).invoke(state)
