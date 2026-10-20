# Upwork Job Copilot (Chrome extension + FastAPI/Postgres + LangGraph + Claude)

## 1. Start the backend
Data lives in a Supabase Postgres database (tables are created automatically on first start).
```bash
cd backend
cp .env.example .env        # set DATABASE_URL (Supabase session pooler URL) and API_TOKEN
python -m venv .venv && .venv\Scripts\activate   # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload   # API on http://localhost:8000
```

### Deploy to Render
Push the repo to GitHub, then in Render: **New -> Blueprint** and pick the repo (uses `render.yaml`), or create a
**Web Service** manually with root directory `backend`, build `pip install -r requirements.txt`, start
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Set `DATABASE_URL`, `API_TOKEN` and `ANTHROPIC_API_KEY` env vars. Use Supabase's
**Session pooler** URL — the direct `db.<ref>.supabase.co` host is IPv6-only and Render can't reach it.

## 2. Load the extension
1. Chrome -> `chrome://extensions` -> turn on Developer mode -> **Load unpacked** -> pick the `extension/` folder.
2. The settings page opens on install. Fill in backend URL, backend token (same as `API_TOKEN`) and your profile. Click **Save**.
3. Pin the icon (puzzle piece -> pin). A **!** badge shows until setup is complete.

## 3. Use it
Open an Upwork job -> click the icon -> **Start**. You get: APPLY / MAYBE / SKIP, reply chance, win chance, profile fit,
competition, client quality, fake risk, every signal checked, red flags, and what could not be verified.
Then **Write proposal**. On the Apply page, **Insert into Apply form** fills the box; you review and press Send yourself.
Track the result (applied / interview / hired / rejected / no reply). Rejected or no-reply triggers an AI post-mortem; the next
proposal for the same or similar jobs uses it (plus any winning proposals) and changes hook and angle.

## How it works
- `extension/content.js` reads the page you are viewing (scrolls to load client history), sends raw text to the backend.
- `backend/app/parser.py` extracts facts (proposals, invites, interviewing, spend, hires, hire rate, rating, country...).
- `backend/app/scoring.py` rule engine from your hooks doc: no invites, no interviewing, <10 proposals, spend vs hires,
  100% hire rate check, unverified payment OK for new clients, prefer USA, scam patterns (Telegram, gift cards, free samples).
- `backend/app/agents/graph.py` LangGraph: score_rules -> load_history (Postgres full-text similar jobs, win rate) ->
  research (Claude web search) -> analyst; proposal mode: writer <-> critic loop (banned words, length, 4 bullets, question, case study).
- Postgres tables: `jobs` (everything scraped, parsed, analysis, status) and `proposals` (versions, hook, outcome, lesson).

## Honest limits
- Upwork changes its HTML. Facts are parsed from page text with regexes in `parser.py`; if a field shows blank, tweak the
  regex (no extension reload needed). I could not test against live Upwork pages, so expect a first-run tweak or two.
- Reply/win chances are estimates from the signals and your own history, not guarantees. They get better as you log outcomes.
- The extension only reads pages you open and never clicks Apply/Send. Automated bulk scraping can violate Upwork's Terms of Use.
- Your Anthropic key lives only on the backend (`ANTHROPIC_API_KEY` env var); the extension never sees it. Use HTTPS if you host it remotely.
- Default model is `claude-sonnet-5-5`; change `ANTHROPIC_MODEL` in `.env`.
