from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import require_recruiter, require_candidate, get_current_user
from app.models import (
    Application,
    ApplicationSkillMatch,
    ApplicationMessage,
    ApplicationStatus,
    Candidate,
    CandidateSkill,
    CandidateExperience,
    CandidateEducation,
    Job,
    User,
    MessageSender,
)
from app.schemas import (
    ApplicationCreate,
    ApplicationListItem,
    ApplicationDetail,
    ApplicationStatusUpdate,
    ApplicationDecision,
    ApplicationMessageIn,
    ApplicationMessageOut,
    MyApplicationOut,
    CandidateListItem,
    JobBrief,
)
from app.ai_service import analyze_resume
from app.pdf_extraction import extract_resume_text

router = APIRouter(prefix="/api/applications", tags=["Applications"])


def _application_query(db: Session):
    return db.query(Application).options(
        joinedload(Application.candidate).joinedload(Candidate.skills),
        joinedload(Application.candidate).joinedload(Candidate.experiences),
        joinedload(Application.candidate).joinedload(Candidate.educations),
        joinedload(Application.job),
        joinedload(Application.skill_matches),
        joinedload(Application.messages),
    )


def application_to_list_item(app: Application) -> ApplicationListItem:
    return ApplicationListItem(
        id=app.id,
        candidate=CandidateListItem.model_validate(app.candidate),
        job=JobBrief.model_validate(app.job),
        ai_match_score=app.ai_match_score,
        status=app.status,
        applied_at=app.applied_at,
    )


def _parse_skills(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


def _apply_ai_analysis_to_application(db: Session, application: Application, job: Job, analysis: dict) -> None:
    """Stores the AI analysis result on the application and its matched/missing skill tags."""
    application.ai_match_score = analysis["score"]
    application.ai_recommendation = analysis["recommendation"]

    db.query(ApplicationSkillMatch).filter(ApplicationSkillMatch.application_id == application.id).delete()
    for skill in analysis["matched_skills"]:
        db.add(ApplicationSkillMatch(application_id=application.id, skill=skill, matched=True))
    for skill in analysis["missing_skills"]:
        db.add(ApplicationSkillMatch(application_id=application.id, skill=skill, matched=False))


def _sync_candidate_profile_from_ai(db: Session, candidate: Candidate, analysis: dict) -> None:
    """
    Merges AI-extracted skills/experience/education (parsed from the resume PDF) into the
    candidate's profile so they show up on the candidate-details page, without duplicating
    entries the candidate already has.
    """
    # 1. المهارات (Skills) ✨
    existing_skill_names = {s.skill.lower() for s in db.query(CandidateSkill).filter(CandidateSkill.candidate_id == candidate.id).all()}
    
    for skill in analysis.get("extracted_skills", []):
        if isinstance(skill, str):
            cleaned_skill = skill.strip()
            if cleaned_skill and cleaned_skill.lower() not in existing_skill_names:
                db.add(CandidateSkill(candidate_id=candidate.id, skill=cleaned_skill))
                existing_skill_names.add(cleaned_skill.lower())

    # 2. الخبرات (Experiences) ✨ (دعم المفرد والجمع بمرونة)
    existing_experience_keys = {(e.title.lower(), e.company.lower()) for e in candidate.experiences}
    raw_experiences = analysis.get("experiences") or analysis.get("experience") or analysis.get("extracted_experiences") or []
    
    for exp in raw_experiences:
        if isinstance(exp, dict) and "title" in exp and "company" in exp:
            title = str(exp.get("title", "")).strip()
            company = str(exp.get("company", "")).strip()
            
            if title and company:
                key = (title.lower(), company.lower())
                if key not in existing_experience_keys:
                    db.add(
                        CandidateExperience(
                            candidate_id=candidate.id,
                            title=title,
                            company=company,
                            description=exp.get("description"),
                            start_date=str(exp.get("start_date", "N/A")),
                            end_date=str(exp.get("end_date", "")) if exp.get("end_date") else None,
                            is_current=exp.get("is_current", False),
                        )
                    )
                    existing_experience_keys.add(key)

    # 3. التعليم (Education) ✨ (دعم تحويل graduation_year بأمان)
    existing_education_keys = {(e.degree.lower(), e.institution.lower()) for e in candidate.educations}
    raw_education = analysis.get("education") or analysis.get("educations") or analysis.get("extracted_education") or []
    
    for edu in raw_education:
        if isinstance(edu, dict) and "degree" in edu and "institution" in edu:
            degree = str(edu.get("degree", "")).strip()
            institution = str(edu.get("institution", "")).strip()
            
            if degree and institution:
                key = (degree.lower(), institution.lower())
                if key not in existing_education_keys:
                    # تحويل graduation_year برفق إلى Integer إذا أمكن
                    grad_year = edu.get("graduation_year")
                    parsed_year = None
                    if grad_year:
                        try:
                            # في حال كان التاريخ النصي مثل "2026" أو يحتوي أرقام
                            import re
                            years = re.findall(r'\b\d{4}\b', str(grad_year))
                            if years:
                                parsed_year = int(years[-1])
                        except Exception:
                            parsed_year = None

                    db.add(
                        CandidateEducation(
                            candidate_id=candidate.id,
                            degree=degree,
                            institution=institution,
                            graduation_year=parsed_year,
                        )
                    )
                    existing_education_keys.add(key)
@router.post("", response_model=ApplicationDetail, status_code=status.HTTP_201_CREATED)
def submit_application(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """
    Matches the 'Apply for this Position' form on /job/jobDetails.
    File uploads (resume/portfolio) must be uploaded first via /api/uploads/* to obtain
    a URL, which the frontend then includes on the candidate profile update, or supplies
    separately - see README for the two-step upload-then-apply flow.
    """
    job = db.get(Job, payload.job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    candidate = db.query(Candidate).filter(Candidate.user_id == current_user.id).first()
    if not candidate:
        candidate = Candidate(user_id=current_user.id, first_name=payload.first_name,
                               last_name=payload.last_name, email=payload.email)
        db.add(candidate)
        db.flush()

    # Keep the candidate profile's contact info in sync with the latest application form submission.
    candidate.first_name = payload.first_name
    candidate.last_name = payload.last_name
    candidate.email = payload.email
    candidate.phone = payload.phone
    candidate.address = payload.address
    candidate.country = payload.country

    existing = (
        db.query(Application)
        .filter(Application.job_id == job.id, Application.candidate_id == candidate.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You have already applied to this job")

    skills = _parse_skills(payload.professional_skills)
    existing_skill_names = {s.skill.lower() for s in candidate.skills}
    for skill in skills:
        if skill.lower() not in existing_skill_names:
            db.add(CandidateSkill(candidate_id=candidate.id, skill=skill))
            existing_skill_names.add(skill.lower())

    application = Application(
        job_id=job.id,
        candidate_id=candidate.id,
        portfolio_link=payload.portfolio_link,
        resume_url=payload.resume_url,
        portfolio_file_url=payload.portfolio_file_url,
        professional_skills_raw=payload.professional_skills,
        years_of_experience=payload.years_of_experience,
        current_monthly_salary=payload.current_monthly_salary,
        expected_monthly_salary=payload.expected_monthly_salary,
        status=ApplicationStatus.NEW,
    )
    db.add(application)
    db.flush()

    # Read the actual resume PDF (uploaded moments earlier via /api/uploads/resume) and run
    # it through the AI analysis service, instead of only comparing the typed-in skills field.
    resume_text = extract_resume_text(payload.resume_url)
    analysis = analyze_resume(job, resume_text, skills)

    _apply_ai_analysis_to_application(db, application, job, analysis)
    _sync_candidate_profile_from_ai(db, candidate, analysis)

    db.commit()

    application = _application_query(db).filter(Application.id == application.id).first()
    return application


@router.get("/me", response_model=list[MyApplicationOut])
def my_applications(db: Session = Depends(get_db), current_user: User = Depends(require_candidate)):
    """Powers the /applications ('My Applications') page."""
    candidate = db.query(Candidate).filter(Candidate.user_id == current_user.id).first()
    if not candidate:
        return []
    apps = (
        _application_query(db)
        .filter(Application.candidate_id == candidate.id)
        .order_by(Application.applied_at.desc())
        .all()
    )
    return apps


@router.get("", response_model=list[ApplicationListItem])
def list_applications(
    search: str | None = Query(default=None, description="Search by candidate name or position"),
    status_filter: ApplicationStatus | None = Query(default=None, alias="status"),
    job_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter),
):
    """Powers the /dashboard Applicants table."""
    query = _application_query(db)

    if status_filter:
        query = query.filter(Application.status == status_filter)
    if job_id:
        query = query.filter(Application.job_id == job_id)
    if search:
        like = f"%{search}%"
        query = query.join(Candidate).join(Job).filter(
            or_(
                Candidate.first_name.ilike(like),
                Candidate.last_name.ilike(like),
                Job.title.ilike(like),
            )
        )

    apps = query.order_by(Application.applied_at.desc()).all()
    return [application_to_list_item(a) for a in apps]


@router.get("/{application_id}", response_model=ApplicationDetail)
def get_application(
    application_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Powers the /dashboard/candidate-details page."""
    application = _application_query(db).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    is_owner = application.candidate.user_id == current_user.id
    if current_user.role.value != "recruiter" and not is_owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this application")
    return application


@router.patch("/{application_id}/status", response_model=ApplicationDetail)
def update_status(
    application_id: str,
    payload: ApplicationStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter),
):
    """Moves a candidate along the pipeline (new -> under_review -> shortlisted -> interview -> offered)."""
    application = db.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    application.status = payload.status
    db.commit()

    return _application_query(db).filter(Application.id == application_id).first()


@router.patch("/{application_id}/decision", response_model=ApplicationDetail)
def decide_application(
    application_id: str,
    payload: ApplicationDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter),
):
    """Powers the Accept / Reject buttons on the candidate-details Decision panel."""
    application = db.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    application.status = payload.decision
    application.decided_at = datetime.now(timezone.utc)
    application.decided_by_id = current_user.id
    db.commit()

    return _application_query(db).filter(Application.id == application_id).first()


@router.post("/{application_id}/messages", response_model=ApplicationMessageOut, status_code=status.HTTP_201_CREATED)
def send_message(
    application_id: str,
    payload: ApplicationMessageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Powers the 'Message from HR' block on the candidate My Applications page."""
    application = db.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    is_owner = application.candidate.user_id == current_user.id
    if current_user.role.value != "recruiter" and not is_owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to message here")

    sender = MessageSender.HR if current_user.role.value == "recruiter" else MessageSender.CANDIDATE
    message = ApplicationMessage(application_id=application.id, sender=sender, message=payload.message)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@router.get("/{application_id}/messages", response_model=list[ApplicationMessageOut])
def list_messages(
    application_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    application = db.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    is_owner = application.candidate.user_id == current_user.id
    if current_user.role.value != "recruiter" and not is_owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view these messages")

    return application.messages


@router.post("/{application_id}/recompute-score", response_model=ApplicationDetail)
def recompute_score(
    application_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_recruiter)
):
    """
    Reruns the AI resume analysis: re-extracts the resume PDF text and re-analyzes it
    against the job, e.g. after the job's requirements/skills changed.
    """
    application = _application_query(db).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    fallback_skills = [s.skill for s in application.candidate.skills] or _parse_skills(
        application.professional_skills_raw or ""
    )
    resume_text = extract_resume_text(application.resume_url)
    analysis = analyze_resume(application.job, resume_text, fallback_skills)

    _apply_ai_analysis_to_application(db, application, application.job, analysis)
    _sync_candidate_profile_from_ai(db, application.candidate, analysis)

    db.commit()
    return _application_query(db).filter(Application.id == application_id).first()
