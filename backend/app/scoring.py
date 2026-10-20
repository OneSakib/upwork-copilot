"""Deterministic rule engine. Encodes the 'Job Scenario' checklist from the hooks doc plus common fake-client signals.
Every signal is explainable, so the popup can show WHY a job scored the way it did."""

PROPOSAL_COMPETITION = {"less than 5": 92, "5 to 10": 78, "10 to 15": 58, "15 to 20": 42, "20 to 50": 22, "50+": 6}
TIER1 = {"United States", "United Kingdom", "Canada", "Australia", "Germany", "Netherlands", "Sweden", "Norway",
         "Denmark", "Ireland", "Switzerland", "New Zealand", "Singapore", "United Arab Emirates"}


def _clamp(v, lo=0, hi=100):
    return max(lo, min(hi, int(round(v))))


def evaluate(p: dict, profile: dict) -> dict:
    sigs = []

    def add(level, name, detail):
        sigs.append({"level": level, "name": name, "detail": detail})

    fake = 0
    hard_stop, hard_reason = False, None

    if p.get("closed"):
        hard_stop, hard_reason = True, "The page says this job is closed / no longer available."
        add("bad", "Job closed", hard_reason)

    # ---------- competition ----------
    br = (p.get("proposals_bracket") or "").lower()
    comp = PROPOSAL_COMPETITION.get(br)
    if comp is None:
        comp = 50
        add("info", "Proposal count unknown", "Could not read the proposals bracket from the page.")
    else:
        lvl = "good" if comp >= 75 else "warn" if comp >= 40 else "bad"
        add(lvl, f"Proposals: {p['proposals_bracket']}", "Under 10 proposals is your target." if comp >= 75 else "More competition means a lower reply chance.")

    inv = p.get("invites_sent")
    if inv == 0:
        add("good", "No invites sent", "Client has not invited anyone yet.")
    elif inv:
        comp -= min(25, inv * 4)
        add("warn" if inv < 5 else "bad", f"{inv} invites sent", "Client is already reaching out to specific freelancers.")

    iv = p.get("interviewing")
    if iv == 0:
        add("good", "Nobody interviewing", "No one has been shortlisted yet.")
    elif iv:
        comp -= min(35, iv * 12)
        add("warn" if iv < 3 else "bad", f"{iv} being interviewed", "Client may already be close to deciding.")

    if p.get("job_hires"):
        comp -= 35
        add("warn", f"{p['job_hires']} hire(s) already made on this post", "The job may be filled or nearly filled. Check before spending Connects.")

    if p.get("last_viewed"):
        add("info", f"Last viewed by client: {p['last_viewed']}", "Recent views mean an active client.")

    # ---------- client quality ----------
    cq = 50
    ts, hires, posted = p.get("total_spent"), p.get("total_hires"), p.get("jobs_posted")
    mm = p.get("member_months")
    new_client = (posted in (None, 0)) or (mm is not None and mm <= 2)

    pv = p.get("payment_verified")
    if pv is True:
        cq += 15
        add("good", "Payment method verified", "")
    elif pv is False:
        if new_client:
            cq -= 3
            add("info", "Payment not verified, but client is new", "Your rule: worth trying when the client just joined.")
        else:
            cq -= 18
            fake += 12
            add("warn", "Payment not verified", "Established client with no verified payment is a risk.")

    if ts is not None:
        if ts >= 100_000: cq += 20
        elif ts >= 10_000: cq += 15
        elif ts >= 1_000: cq += 8
        elif ts > 0: cq += 2
        add("good" if ts >= 1_000 else "info", f"${ts:,.0f} total spent", "")
        if ts == 0 and (posted or 0) > 0:
            cq -= 10
            fake += 10
            add("warn", "Posted jobs but spent $0", "Never paid for anything on Upwork.")
    if ts == 0 and (hires or 0) > 0:
        fake += 35
        add("bad", "Hires recorded but $0 spent", "Spend vs hires does not add up. Classic fake/inflated client pattern.")

    spend_per_hire = p.get("avg_spend_per_hire")
    if spend_per_hire is not None and (hires or 0) >= 3 and spend_per_hire < 25:
        cq -= 8
        fake += 8
        add("warn", f"Only ${spend_per_hire:.0f} spent per hire", "Many hires with tiny spend can mean micro-tasks or inflated hire counts.")
    elif spend_per_hire is not None:
        add("info", f"${spend_per_hire:,.0f} average spend per hire", "")

    rate = p.get("hire_rate")
    if rate is not None:
        if rate >= 100 and (hires or 0) >= 1:
            fake += 15
            add("warn", "100% hire rate", "Your rule: always verify. Check total spent, reviews, and whether the work history looks real.")
        elif rate <= 20 and (posted or 0) >= 5:
            cq -= 12
            add("warn", f"Low hire rate ({rate}%)", "Posts a lot but rarely hires, so a likely time-waster.")
        elif 40 <= rate < 100:
            cq += 8
            add("good", f"{rate}% hire rate", "Healthy history of actually hiring.")

    rt = p.get("client_rating")
    if rt is not None:
        if rt >= 4.8: cq += 10
        elif rt >= 4.5: cq += 4
        elif rt < 4.0:
            cq -= 15
        add("good" if rt >= 4.5 else "bad" if rt < 4.0 else "info", f"Client rating {rt} ({p.get('client_reviews', '?')} reviews)", "")
    elif (hires or 0) >= 5:
        fake += 8
        add("warn", "Many hires but no reviews", "")

    country = p.get("client_country")
    prefs = set(profile.get("preferred_countries") or ["United States"])
    if country:
        if country in prefs or country == "United States":
            cq += 8
            add("good", f"Client country: {country}", "Matches your preferred markets.")
        elif country in TIER1:
            cq += 4
            add("info", f"Client country: {country}", "")
        else:
            add("info", f"Client country: {country}", "")
    lr = p.get("location_restriction")
    my = (profile.get("country") or "").lower()
    if lr and my and my not in lr.lower():
        hard_stop, hard_reason = True, f"Job is restricted to freelancers in: {lr}."
        add("bad", "Location restriction", hard_reason)

    # budget
    fb = p.get("fixed_budget")
    if fb is not None:
        minb = profile.get("min_fixed_budget") or 0
        if fb < max(minb, 30):
            cq -= 8
            add("warn", f"Low fixed budget (${fb:,.0f})", "Below your minimum." if minb else "Very low for professional work.")
        else:
            add("info", f"Fixed budget ${fb:,.0f}", "")
    if p.get("hourly_max") and profile.get("hourly_rate") and p["hourly_max"] < profile["hourly_rate"]:
        cq -= 8
        add("warn", f"Hourly max ${p['hourly_max']:.0f} is below your rate (${profile['hourly_rate']:.0f})", "")

    # text-based scam checks
    for flag in p.get("scam_flags", []):
        fake += 40
        add("bad", "Scam pattern in description", flag)
    dc = p.get("description_chars", 0)
    if 0 < dc < 80:
        fake += 10
        add("warn", "Very short description", "Vague posts are often low-effort or fake.")

    # ---------- freshness ----------
    pm = p.get("posted_minutes_ago")
    if pm is None:
        fresh = 50
    else:
        fresh = 95 if pm < 30 else 85 if pm < 120 else 70 if pm < 360 else 50 if pm < 1440 else 30 if pm < 4320 else 15
        add("good" if fresh >= 70 else "info" if fresh >= 40 else "warn", f"Posted {pm // 60}h {pm % 60}m ago" if pm < 1440 else f"Posted {pm // 1440} day(s) ago",
            "Early applicants get seen first." if fresh >= 70 else "")

    if p.get("connects_required"):
        add("info", f"{p['connects_required']} Connects to apply", "")

    comp, cq, fresh, fake = _clamp(comp), _clamp(cq), _clamp(fresh), _clamp(fake)
    rule_score = _clamp(0.35 * comp + 0.30 * cq + 0.15 * fresh + 0.20 * (100 - fake))
    order = {"bad": 0, "warn": 1, "good": 2, "info": 3}
    sigs.sort(key=lambda s: order[s["level"]])
    return {
        "competition": comp, "client_quality": cq, "freshness": fresh, "fake_risk": fake,
        "rule_score": rule_score, "signals": sigs, "hard_stop": hard_stop, "hard_stop_reason": hard_reason,
    }
