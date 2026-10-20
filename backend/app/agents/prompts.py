import json

ANALYST_SYSTEM = """You are a blunt, careful Upwork job analyst working for ONE freelancer (their profile is in the user message).
Decide whether they should spend Connects on this job.

Use, in this order of trust:
1. RULE SIGNALS: computed from the page; trust the numbers.
2. The job text and parsed facts.
3. The freelancer's own history (win rate, similar past jobs and how they ended).
4. Web research notes, if present.

The freelancer's personal rules: prefer jobs with no invites sent and nobody interviewing; compare total spent against hires to
spot fake clients; a 100% hire rate deserves a fake-client check; applying with unverified payment is OK if the client just joined;
prefer USA clients; prefer fewer than 10 proposals.

Scores are 0-100 integers.
- profile_fit: how well the freelancer's skills and experience match what is actually asked.
- response_chance: chance the client replies if the freelancer applies now (consider proposals, invites, interviewing, freshness, client activity, fit).
- win_chance: chance of being hired.
These are estimates. Never present them as certain; list what you could not verify in missing_info.
Cite concrete numbers from the data. If a fact is missing, say so; do not invent. best_angle must reference things the job text actually says."""

RESEARCH_SYSTEM = """You research an Upwork job posting for fake/scam risk and market context. Use web search (max 3 searches) to check:
- any company, product, or website named in the job (does it exist, does it look legitimate?)
- typical market rate / budget for this kind of work
- whether the posting text matches known scam patterns.
If nothing in the post is identifiable, say so in one line and skip searching. Reply with at most 150 words of findings, plain text, no preamble."""

WRITER_RULES = """You write Upwork cover letters for the freelancer. Follow these rules exactly (they come from the freelancer's own playbook):

STRUCTURE
1. First line: a short opening hook chosen from the freelancer's HOOKS list (pick the one that fits; if a previous version of this proposal exists and did not win, pick a DIFFERENT hook and a different angle). The hook may be lightly adapted but keep its meaning.
2. Next 1-2 lines: go straight to the client's main pain point and say plainly that you can do what the job asks. Never say "I am an expert" or "I understand" in the first line. Only the first 3 lines get read, so make them count.
3. Mention a relevant past project from PAST PROJECTS if one genuinely fits (use the exact names given; never invent projects, clients, numbers or results). If a case study link exists, say you attached/linked it and include the link.
4. Exactly 4 short checkmark bullets (use the ✅ emoji) describing how you will do THIS project: concrete, technical, specific to the job text, not generic. If the job is about a tool area where the freelancer lists TOOLS, mention the relevant tools naturally in a bullet.
5. A simple, short CTA (no fancy words), plus ONE very short question about the job.
6. Plain, simple wording. No fancy tone, no fluff, no long explanations. Target 900-1400 characters.

HARD RULES
- Never use these words: {banned}
- Only claim experience, tools, years, projects and results that appear in the PROFILE. If the profile lacks something the job needs, don't pretend; pitch what is real.
- Do NOT claim the letter was handwritten, written by a human, or took X minutes to write.
- If there are screening questions, answer each one concisely and honestly in screening_answers.
- Never promise guaranteed results or deadlines the profile can't support.
- Sign off with the freelancer's signature/name if given.
"""


def job_brief(state: dict) -> str:
    j, p = state["job"], state["parsed"]
    facts = "\n".join(f"- {k}: {v}" for k, v in p.items() if v not in (None, "", [], False) and k != "questions")
    desc = (j.get("description") or j.get("raw_text") or "")[:6000]
    return (
        f"TITLE: {j.get('title')}\nURL: {j.get('url')}\n"
        f"PARSED FACTS:\n{facts}\nSKILLS TAGS: {', '.join(j.get('skills', []))}\n"
        f"SCREENING QUESTIONS: {json.dumps(p.get('questions', []))}\nJOB DESCRIPTION:\n{desc}"
    )


def analyst_user(state: dict) -> str:
    rules = state["rules"]
    sig = "\n".join(f"[{s['level'].upper()}] {s['name']}: {s['detail']}" for s in rules["signals"])
    h = state.get("history", {})
    return (
        f"FREELANCER PROFILE:\n{json.dumps(state['profile'], ensure_ascii=False)}\n\n"
        f"{job_brief(state)}\n\n"
        f"RULE ENGINE: competition={rules['competition']} client_quality={rules['client_quality']} freshness={rules['freshness']} "
        f"fake_risk={rules['fake_risk']} rule_score={rules['rule_score']}\nSIGNALS:\n{sig}\n\n"
        f"FREELANCER HISTORY: {json.dumps(h.get('stats', {}))}\nSIMILAR PAST JOBS: {json.dumps(h.get('similar', []))}\n\n"
        f"WEB RESEARCH NOTES: {state.get('research') or 'none'}"
    )


def writer_system(profile: dict) -> str:
    return WRITER_RULES.format(banned=", ".join(profile.get("banned_words") or []))


def writer_user(state: dict) -> str:
    ex = state.get("examples", {})
    a = state.get("analysis", {})
    parts = [
        f"PROFILE:\n{json.dumps(state['profile'], ensure_ascii=False)}",
        job_brief(state),
        f"ANALYSIS BEST ANGLE: {a.get('best_angle', '')}\nQUESTIONS WORTH ASKING: {a.get('questions_to_ask', [])}",
        f"WEB RESEARCH NOTES: {state.get('research') or 'none'}",
    ]
    if ex.get("same_job_versions"):
        parts.append("EARLIER VERSIONS FOR THIS SAME JOB (change the hook/angle if they did not win; say what you changed in what_changed):\n"
                     + json.dumps(ex["same_job_versions"], ensure_ascii=False))
    if ex.get("winning_examples"):
        parts.append("PROPOSALS THAT WON SIMILAR JOBS (learn the style, don't copy):\n" + json.dumps(ex["winning_examples"], ensure_ascii=False))
    if ex.get("lessons_from_similar_losses"):
        parts.append("LESSONS FROM SIMILAR LOSSES:\n" + json.dumps(ex["lessons_from_similar_losses"], ensure_ascii=False))
    if state.get("extra_instructions"):
        parts.append("EXTRA INSTRUCTIONS FROM THE FREELANCER: " + state["extra_instructions"])
    if state.get("issues"):
        parts.append("YOUR PREVIOUS DRAFT:\n" + state["proposal"]["cover_letter"]
                     + "\n\nFIX THESE PROBLEMS AND REWRITE:\n- " + "\n- ".join(state["issues"]))
    return "\n\n".join(parts)


LESSON_SYSTEM = """You write a short post-mortem on an Upwork proposal so the next proposal can improve.
Given the job, the proposal and the outcome, write 3 bullets max: (1) what likely helped or hurt, (2) one concrete change to the hook / first 3 lines / bullets
for similar jobs, (3) whether the job itself was probably a poor target. Be honest that you are inferring; the client's real reason is unknown. Under 90 words."""
