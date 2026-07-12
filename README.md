# ITG Career System — Backend

FastAPI + SQLAlchemy + PostgreSQL backend for the ITG Career System frontend
(`Itg-Career-System-Project`, Next.js/React).

## Stack
Python · FastAPI · SQLAlchemy 2.0 (ORM) · PostgreSQL · Pydantic v2 · Alembic · JWT (python-jose + passlib)

## Project layout
```
app/
  main.py            FastAPI app, CORS, router wiring, static /uploads mount
  config.py          Settings loaded from environment (.env)
  database.py        Engine, SessionLocal, Base, get_db dependency
  models.py          SQLAlchemy ORM models
  schemas.py         Pydantic request/response schemas
  security.py        Password hashing + JWT helpers
  dependencies.py    get_current_user / require_recruiter / require_candidate guards
  matching_service.py  AI match-score / skill-analysis computation
  routes/
    auth.py          /api/auth/*
    jobs.py          /api/jobs/*
    candidates.py    /api/candidates/*
    applications.py  /api/applications/*
    uploads.py       /api/uploads/*
alembic/             Migrations (env.py wired to app settings/models)
uploads/             Local storage for resumes/portfolios (served at /uploads/*)
```

## Setup

1. Create a PostgreSQL database:
   ```bash
   createdb itg_career
   ```

2. Copy the env file and fill in real values:
   ```bash
   cp .env.example .env
   # edit DATABASE_URL and SECRET_KEY
   ```

3. Install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate       # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. Create the database schema. Either:
   - Quick start (creates tables directly from models, no migration history):
     the app does this automatically on startup via `Base.metadata.create_all`.
   - Recommended for real projects — generate and apply a migration:
     ```bash
     alembic revision --autogenerate -m "initial schema"
     alembic upgrade head
     ```

5. Run the server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

6. Interactive API docs: `http://localhost:8000/docs`

## Auth model

Two roles: `recruiter` (HR/admin, matches the Navbar's hardcoded "abeer Mourtaja" user
on `/dashboard` and `/jobPositions`) and `candidate` (matches `/job` and `/applications`).
Sign up via `POST /api/auth/signup` with `role`, log in via `POST /api/auth/login`
(OAuth2 password flow), then send `Authorization: Bearer <token>` on subsequent requests.

## Apply flow (matches `/job/jobDetails`)

The form has file inputs (resume, portfolio) alongside text fields. Since a single
JSON `POST /api/applications` can't carry files, the flow is two-step, exactly how a
real frontend integration would call it:

1. `POST /api/uploads/resume` (multipart, field `file`) → `{ "url": "/uploads/resumes/xyz.pdf" }`
2. `POST /api/uploads/portfolio` (multipart, optional) → `{ "url": "/uploads/portfolios/xyz.pdf" }`
3. `POST /api/applications` with the rest of the form fields plus the returned `resume_url`
   (and optional `portfolio_file_url`)

## AI Resume Analysis (PDF-based)

When a candidate applies with a PDF resume, the backend now does a **real** analysis
instead of comparing only the typed-in "Professional Skills" field:

1. `app/pdf_extraction.py` opens the uploaded PDF (via `pdfplumber`) and extracts its
   full text. Only `.pdf` resumes are text-extracted — `.doc`/`.docx` are stored and
   downloadable as before but not parsed (would need `python-docx`, out of scope here).
   Scanned/image-only PDFs with no text layer yield empty text and fall back gracefully.
2. `app/ai_service.py` sends that text, plus the job's title/summary/requirements/skills,
   to Claude (Anthropic API) and asks for a structured JSON result: match score,
   matched/missing skills, all skills found in the resume, a hiring recommendation, and
   parsed **work experience** and **education** entries.
3. `app/routes/applications.py` stores the score/recommendation/skill tags on the
   `Application`, and merges the extracted skills/experience/education into the
   candidate's profile (`CandidateSkill`/`CandidateExperience`/`CandidateEducation`) —
   deduplicated against what's already there — so they appear on the candidate-details
   page exactly like manually-entered profile data.
4. `POST /api/applications/{id}/recompute-score` re-runs the same pipeline (re-reads the
   stored resume PDF) for an existing application, e.g. after the job's requirements change.

**Configuration required:** set `ANTHROPIC_API_KEY` in `.env` (get one at
console.anthropic.com) and optionally `ANTHROPIC_MODEL` (defaults to
`claude-sonnet-4-5-20250929` — check Anthropic's docs for the latest model name).
**If `ANTHROPIC_API_KEY` is left empty, or the API call fails for any reason** (network,
rate limit, malformed response), the backend automatically falls back to a deterministic
skill-overlap heuristic so applications never fail to submit — in that case, experience/
education won't be auto-populated from the resume, only the score/recommendation will be
computed from the "Professional Skills" text field.

## Known gaps between this backend and the current frontend code

These are called out explicitly per the task instructions rather than silently guessed:

1. **No dynamic IDs in the frontend routes.** `dashboard/candidate-details` and
   `job/jobDetails` are static Next.js routes with no `[id]` segment — every "View
   Details" / "View & Apply" click currently shows the same hardcoded card regardless
   of which row was clicked. The API is built correctly RESTfully
   (`/api/applications/{id}`, `/api/jobs/{id}`), but wiring the frontend to pass the
   real id (e.g. `router.push(\`/dashboard/candidate-details/${id}\`)` with a
   `[id]/page.tsx`) is a frontend change outside this backend task.
2. **The "Add New Position" modal has no fields for tags/skills or itemized
   requirements**, even though the public job board and job detail page display both.
   The API supports `requirements` and `skills` on job create/update since they're
   needed for the AI match logic and detail page, but no current form field writes to
   them — this will need a small frontend addition.
3. **All dashboard/job data in the frontend is hardcoded markup**, not fetched from
   any API or mock data file, so there's no existing fetch layer to match field-for-field
   — the schemas here were derived from the JSX structure/labels themselves.
