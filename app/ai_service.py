"""
Analyzes an extracted resume text against a job's requirements to produce the data
shown on the candidate-details page: AI Match Score, matched/missing skills, the AI
recommendation, and (new) structured experience/education/skills parsed straight out
of the CV.

If ANTHROPIC_API_KEY is not configured, or the API call / JSON parsing fails for any
reason, this falls back to a transparent, deterministic skill-overlap heuristic so the
application flow never breaks - it just won't have CV-derived experience/education in
that case (only whatever the candidate typed into "Professional Skills" on the form).
"""

import json
import re
from datetime import date

from app.config import settings
from app.models import Job

try:
    import anthropic
except ImportError:  # pragma: no cover - anthropic is a hard requirement, but degrade gracefully
    anthropic = None


def _normalize(skill: str) -> str:
    return skill.strip().lower()


def _heuristic_analysis(job: Job, fallback_skills: list[str]) -> dict:
    """Deterministic skill-overlap scorer, used when no real AI call is available."""
    required_skills = [s.skill for s in job.skills if s.is_required] or [s.skill for s in job.skills]
    normalized_required = {_normalize(s): s for s in required_skills}
    normalized_candidate = {_normalize(s) for s in fallback_skills}

    matched = [orig for norm, orig in normalized_required.items() if norm in normalized_candidate]
    missing = [orig for norm, orig in normalized_required.items() if norm not in normalized_candidate]

    score = round(len(matched) / len(normalized_required) * 100) if normalized_required else 50

    if score >= 90:
        recommendation = "Exceptional match. Strongly recommend advancing to a final interview."
    elif score >= 75:
        recommendation = "Strong match. Most required skills are present. Recommend moving to interview."
    elif score >= 50:
        recommendation = "Moderate match. Some required skills are missing; consider a screening call."
    else:
        recommendation = "Weak match on required skills for this role."

    return {
        "score": score,
        "matched_skills": matched,
        "missing_skills": missing,
        "extracted_skills": fallback_skills,
        "recommendation": recommendation,
        "experience": [],
        "education": [],
    }


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _build_prompt(job: Job, resume_text: str, fallback_skills: list[str]) -> str:
    requirements = "\n".join(f"- {r.text}" for r in job.requirements) or "(none listed)"
    required_skills = ", ".join(s.skill for s in job.skills) or "(none listed)"
    stated_skills = ", ".join(fallback_skills) or "(none listed)"

    return f"""You are an ATS resume-screening assistant. Analyze the candidate's resume text
below against the job, and respond with ONLY a single JSON object (no markdown fences, no
prose before or after) matching exactly this schema:

{{
  "match_score": <integer 0-100, how well the candidate fits this specific job>,
  "matched_skills": [<job-required skills the resume demonstrates>],
  "missing_skills": [<job-required skills the resume does NOT demonstrate>],
  "extracted_skills": [<all technical/professional skills found anywhere in the resume>],
  "recommendation": "<2-3 sentence hiring recommendation>",
  "experience": [
    {{"title": "<job title>", "company": "<company name>", "start_date": "<YYYY-MM-DD or YYYY-MM or YYYY, best guess>", "end_date": "<YYYY-MM-DD or null>", "is_current": <true/false>, "description": "<1-2 sentence summary of the role>"}}
  ],
  "education": [
    {{"degree": "<degree/field>", "institution": "<school name>", "graduation_year": <integer or null>}}
  ]
}}

Rules:
- Only include experience/education entries that are actually present in the resume text.
- If the resume text is empty, garbled, or clearly not a resume, return empty lists and a match_score based only on "Candidate-stated skills" below, with a recommendation noting the resume could not be read.
- Do not invent companies, dates, or degrees that aren't in the text.

Job title: {job.title}
Job department: {job.department}
Job summary: {job.summary}
Job requirements:
{requirements}
Job required skills: {required_skills}

Candidate-stated skills (from the application form, use only if resume text is empty): {stated_skills}

Resume text:
\"\"\"
{resume_text or "(no resume text extracted)"}
\"\"\"
"""


def _parse_date(value) -> date | None:
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            parsed = date(*_pad_date_parts(value, fmt))
            return parsed
        except (ValueError, TypeError):
            continue
    return None


def _pad_date_parts(value: str, fmt: str) -> list[int]:
    parts = value.split("-")
    if fmt == "%Y-%m-%d" and len(parts) == 3:
        return [int(parts[0]), int(parts[1]), int(parts[2])]
    if fmt == "%Y-%m" and len(parts) == 2:
        return [int(parts[0]), int(parts[1]), 1]
    if fmt == "%Y" and len(parts) == 1:
        return [int(parts[0]), 1, 1]
    raise ValueError("format mismatch")


def analyze_resume(job: Job, resume_text: str, fallback_skills: list[str]) -> dict:
    """
    Returns a dict with: score, matched_skills, missing_skills, extracted_skills,
    recommendation, experience (list of dicts with parsed `date` objects), education.
    """
    if not settings.ANTHROPIC_API_KEY or anthropic is None:
        return _heuristic_analysis(job, fallback_skills)

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": _build_prompt(job, resume_text, fallback_skills)}],
        )
        raw_text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        data = json.loads(_strip_code_fences(raw_text))

        experience = []
        for exp in data.get("experience", []):
            start = _parse_date(exp.get("start_date"))
            if not start or not exp.get("title") or not exp.get("company"):
                continue  # skip incomplete entries rather than guessing
            experience.append(
                {
                    "title": exp["title"],
                    "company": exp["company"],
                    "start_date": start,
                    "end_date": _parse_date(exp.get("end_date")),
                    "is_current": bool(exp.get("is_current", False)),
                    "description": exp.get("description"),
                }
            )

        education = []
        for edu in data.get("education", []):
            if not edu.get("degree") or not edu.get("institution"):
                continue
            education.append(
                {
                    "degree": edu["degree"],
                    "institution": edu["institution"],
                    "graduation_year": edu.get("graduation_year"),
                }
            )

        score = int(data.get("match_score", 0))
        score = max(0, min(100, score))

        return {
            "score": score,
            "matched_skills": [s for s in data.get("matched_skills", []) if isinstance(s, str)],
            "missing_skills": [s for s in data.get("missing_skills", []) if isinstance(s, str)],
            "extracted_skills": [s for s in data.get("extracted_skills", []) if isinstance(s, str)] or fallback_skills,
            "recommendation": data.get("recommendation") or "No recommendation returned by the model.",
            "experience": experience,
            "education": education,
        }
    except Exception:
        # Any failure (network, auth, malformed JSON, rate limit, etc.) - degrade to the heuristic
        # rather than failing the candidate's application submission.
        return _heuristic_analysis(job, fallback_skills)
