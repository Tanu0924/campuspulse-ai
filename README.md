# CampusPulse AI — multi-department university analytics

## Run locally (Python 3.12)
    python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
    pip install -r requirements.txt -r requirements-dev.txt
    python check.py            # runs all tests; fix anything red before continuing
    python seed.py             # fictional demo data (password for all demo users: Demo@12345)
    streamlit run app.py

Demo logins: rakesh@demo.edu (faculty) · hod.cse@demo.edu (HOD) · admin@demo.edu (admin).
**Change the demo passwords or delete the demo users before real use.**

## AI questions
Create `.streamlit/secrets.toml` (see `.streamlit/secrets.toml.example`) with `ANTHROPIC_API_KEY`. Optional: `ANTHROPIC_MODEL`.

## Deploy on Streamlit Community Cloud
1. Push this folder to a GitHub repo (`.gitignore` already excludes databases and secrets).
2. share.streamlit.io → New app → pick repo, main file `app.py`; Advanced settings → Python 3.12.
3. Advanced settings → Secrets: paste `DATABASE_URL` and `ANTHROPIC_API_KEY`.
4. **Use a hosted PostgreSQL URL** (e.g. Neon/Supabase, `postgresql+psycopg2://...`) and add `psycopg2-binary` to requirements.txt. The Cloud disk is wiped on restart, so the default SQLite file will lose data.
5. First admin: run `python seed.py` locally against the same `DATABASE_URL`, then change that password, or create your own admin row.

## Accounts
Faculty self-register. Admins create HOD/faculty accounts, reset passwords (temporary password, forced change), deactivate users, and see an activity log. No email service is assumed.
