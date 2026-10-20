"""Turns the raw text the extension scraped into structured facts.
Kept in Python (not in the extension) so you can fix a regex without reloading the extension."""
import re
from datetime import datetime, timezone

COUNTRIES = [
    "United States", "United Kingdom", "Canada", "Australia", "Germany", "Netherlands", "Sweden", "Norway",
    "Denmark", "Ireland", "Switzerland", "New Zealand", "Singapore", "United Arab Emirates", "France", "Spain",
    "Italy", "Israel", "Israel", "Saudi Arabia", "Qatar", "India", "Pakistan", "Bangladesh", "Philippines",
    "Nigeria", "Egypt", "Turkey", "Poland", "Ukraine", "Brazil", "Mexico", "South Africa", "Kenya", "Belgium",
    "Austria", "Finland", "Portugal", "Hong Kong", "Japan", "Malaysia", "Indonesia", "Vietnam",
]

SCAM_PATTERNS = {
    "asks to move off Upwork (Telegram/WhatsApp/Skype/email)": r"\b(telegram|whats\s?app|skype|signal app|contact me (at|on|via)|email me at)\b",
    "mentions crypto wallet / gift cards / payment before work": r"\b(gift cards?|crypto wallet|bitcoin|usdt|pay (a )?(small )?(fee|deposit) (first|upfront)|western union)\b",
    "asks for a paid test / free sample of real work": r"\b(free (sample|trial|test)|unpaid (test|trial)|paid training fee)\b",
    "asks for personal/bank/ID details": r"\b(bank (account|details)|passport|social security|ssn|password)\b",
}

MONTHS = {"sept": "Sep"}


def to_num(s):
    if s is None:
        return None
    s = str(s).replace(",", "").replace("$", "").strip().upper()
    mult = 1
    if s.endswith("K"):
        mult, s = 1_000, s[:-1]
    elif s.endswith("M"):
        mult, s = 1_000_000, s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


def _m(pattern, text, flags=re.I):
    return re.search(pattern, text or "", flags)


def _int(pattern, text, flags=re.I):
    m = _m(pattern, text, flags)
    return int(to_num(m.group(1))) if m and to_num(m.group(1)) is not None else None


def _minutes(text):
    if re.search(r"Posted\s+yesterday", text, re.I):
        return 1440
    if re.search(r"Posted\s+last week", text, re.I):
        return 10080
    m = _m(r"Posted\s+(\d+)\s+(minute|hour|day|week|month)s?\s+ago", text)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    return n * {"minute": 1, "hour": 60, "day": 1440, "week": 10080, "month": 43200}[unit]


def _member_months(text):
    m = _m(r"Member since\s*:?\s*([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", text)
    if not m:
        return None
    mon = MONTHS.get(m.group(1).lower(), m.group(1)[:3])
    try:
        d = datetime.strptime(f"{mon} {m.group(2)} {m.group(3)}", "%b %d %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return max(0, int((datetime.now(timezone.utc) - d).days / 30))


def _questions(raw):
    m = _m(r"answer the following questions[^\n]*\n", raw)
    if not m:
        return []
    out = []
    for line in raw[m.end():].splitlines():
        line = line.strip()
        if not line:
            if out:
                break
            continue
        q = re.match(r"^\d+[.)]\s*(.+)", line)
        if q:
            out.append(q.group(1))
        elif out:
            break
    return out[:8]


def parse_job(s: dict) -> dict:
    raw = s.get("raw_text") or ""
    act = s.get("activity_text") or raw
    cli = s.get("client_text") or raw
    desc = s.get("description") or raw
    url = s.get("url") or ""

    uid = _m(r"~(0\d{15,})", url)
    out = {"upwork_id": uid.group(1) if uid else None}

    out["closed"] = bool(_m(
        r"no longer (available|accepting)|job (is )?closed|this job (has been|was) (closed|filled|removed)|job posting (has )?expired|"
        r"this job is private|job not found", raw))

    # ---- activity on the job ----
    pb = _m(r"Proposals[:\s]+(Less than 5|5 to 10|10 to 15|15 to 20|20 to 50|50\+)", act)
    out["proposals_bracket"] = pb.group(1) if pb else None
    out["interviewing"] = _int(r"Interviewing[:\s]+(\d+)", act)
    out["invites_sent"] = _int(r"Invites sent[:\s]+(\d+)", act)
    out["unanswered_invites"] = _int(r"Unanswered invites[:\s]+(\d+)", act)
    out["job_hires"] = _int(r"\bHires[:\s]+(\d+)", act, 0)
    lv = _m(r"Last viewed by client[:\s]+([^\n]+)", act)
    out["last_viewed"] = lv.group(1).strip() if lv else None
    out["posted_minutes_ago"] = _minutes(raw)

    # ---- job details ----
    fixed = _m(r"\$\s*([\d,]+(?:\.\d+)?)\s*[\n ]*Fixed[- ]price", raw) or _m(r"Fixed[- ]price[^$]{0,40}\$\s*([\d,]+(?:\.\d+)?)", raw)
    hourly = _m(r"\$\s*([\d.]+)\s*[-–]\s*\$\s*([\d.]+)\s*[\n ]*Hourly", raw)
    out["budget_type"] = "fixed" if fixed else ("hourly" if hourly or _m(r"\bHourly\b", raw) else None)
    out["fixed_budget"] = to_num(fixed.group(1)) if fixed else None
    out["hourly_min"] = to_num(hourly.group(1)) if hourly else None
    out["hourly_max"] = to_num(hourly.group(2)) if hourly else None
    lvl = _m(r"\b(Entry level|Intermediate|Expert)\b", raw, 0)
    out["experience_level"] = lvl.group(1) if lvl else None
    out["connects_required"] = _int(r"(\d+)\s+Connects", raw) or _int(r"Required Connects[^\d]{0,40}(\d+)", raw)
    lr = _m(r"Only freelancers located in (?:the )?([^\n.]+?) (?:can|may) apply", raw)
    out["location_restriction"] = lr.group(1).strip() if lr else None
    out["featured"] = bool(_m(r"\bFeatured job\b", raw))

    # ---- about the client ----
    pv = None
    if _m(r"payment method not verified|payment unverified|unverified payment", cli):
        pv = False
    elif _m(r"payment method verified", cli):
        pv = True
    out["payment_verified"] = pv
    rt = _m(r"(\d\.\d{1,2})\s*(?:of|out of)\s*([\d,]+)\s*reviews?", cli)
    out["client_rating"] = float(rt.group(1)) if rt else None
    out["client_reviews"] = int(to_num(rt.group(2))) if rt else None
    out["client_country"] = s.get("country") or next((c for c in COUNTRIES if re.search(rf"\b{re.escape(c)}\b", cli)), None)
    out["jobs_posted"] = _int(r"([\d,]+)\s+jobs? posted", cli)
    out["hire_rate"] = _int(r"(\d+)%\s*hire rate", cli)
    out["open_jobs"] = _int(r"(\d+)\s+open jobs?", cli)
    spent = _m(r"\$\s*([\d.,]+\s?[KM]?)\s*total spent", cli)
    out["total_spent"] = to_num(spent.group(1).replace(" ", "")) if spent else None
    th = _m(r"([\d,]+)\s+hires?(?:,\s*([\d,]+)\s+active)?", cli)
    out["total_hires"] = int(to_num(th.group(1))) if th else None
    out["active_hires"] = int(to_num(th.group(2))) if th and th.group(2) else None
    ah = _m(r"\$\s*([\d.,]+)\s*/hr\s*avg hourly rate paid", cli)
    out["avg_hourly_paid"] = to_num(ah.group(1)) if ah else None
    out["hours_billed"] = _int(r"([\d,]+)\s+hours", cli)
    out["member_months"] = _member_months(cli)

    ts, th2 = out["total_spent"], out["total_hires"]
    out["avg_spend_per_hire"] = round(ts / th2, 2) if ts is not None and th2 else None

    # ---- text-based risk flags ----
    flags = [name for name, pat in SCAM_PATTERNS.items() if _m(pat, desc)]
    out["scam_flags"] = flags
    out["description_chars"] = len(desc.strip())
    out["questions"] = _questions(raw)
    return {k: v for k, v in out.items() if v is not None or k in ("payment_verified",)}
