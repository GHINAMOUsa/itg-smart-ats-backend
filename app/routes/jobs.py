from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import require_recruiter, get_optional_user
from app.models import Job, JobRequirement, JobSkill, JobStatus, EmploymentType, User, UserRole
from app.schemas import JobCreate, JobUpdate, JobOut, JobListItem, ApplicationListItem
from app.routes.applications import application_to_list_item

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


def _job_query(db: Session):
    return db.query(Job).options(joinedload(Job.requirements), joinedload(Job.skills), joinedload(Job.applications))


@router.get("", response_model=list[JobListItem])
def list_jobs(
    search: str | None = Query(default=None, description="Search by title, department or location"),
    department: str | None = Query(default=None),
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    employment_type: EmploymentType | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    """
    Powers both:
    - /jobPositions (recruiter): sees all statuses, filter by department + status tabs (All/Open/Closed/Draft)
    - /job (public candidate board): only ever sees Open jobs, filter by search box
    """
    query = _job_query(db)

    is_recruiter = current_user is not None and current_user.role == UserRole.RECRUITER
    if not is_recruiter:
        query = query.filter(Job.status == JobStatus.OPEN)
    elif status_filter is not None:
        query = query.filter(Job.status == status_filter)

    if department:
        query = query.filter(Job.department.ilike(f"%{department}%"))

    if employment_type:
        query = query.filter(Job.employment_type == employment_type)

    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Job.title.ilike(like),
                Job.department.ilike(like),
                Job.location_city.ilike(like),
                Job.location_country.ilike(like),
            )
        )

    jobs = query.order_by(Job.created_at.desc()).all()
    return jobs


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = _job_query(db).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, db: Session = Depends(get_db), current_user: User = Depends(require_recruiter)):
    """Matches the 'Add New Position' modal on /jobPositions."""
    job = Job(
        title=payload.title,
        department=payload.department,
        employment_type=payload.employment_type,
        location_city=payload.location_city,
        location_country=payload.location_country,
        field_of_study=payload.field_of_study,
        salary_range=payload.salary_range,
        summary=payload.summary,
        description=payload.description,
        status=payload.status,
        posted_by_id=current_user.id,
    )
    db.add(job)
    db.flush()

    for i, req_text in enumerate(payload.requirements):
        db.add(JobRequirement(job_id=job.id, text=req_text, position=i))
    for skill in payload.skills:
        db.add(JobSkill(job_id=job.id, skill=skill))

    db.commit()
    db.refresh(job)
    return job


@router.put("/{job_id}", response_model=JobOut)
def update_job(
    job_id: str,
    payload: JobUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter),
):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    update_data = payload.model_dump(exclude_unset=True, exclude={"requirements", "skills"})
    for field, value in update_data.items():
        setattr(job, field, value)

    if payload.requirements is not None:
        db.query(JobRequirement).filter(JobRequirement.job_id == job.id).delete()
        for i, req_text in enumerate(payload.requirements):
            db.add(JobRequirement(job_id=job.id, text=req_text, position=i))

    if payload.skills is not None:
        db.query(JobSkill).filter(JobSkill.job_id == job.id).delete()
        for skill in payload.skills:
            db.add(JobSkill(job_id=job.id, skill=skill))

    db.commit()
    db.refresh(job)
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_recruiter)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    db.delete(job)
    db.commit()


@router.get("/{job_id}/applicants", response_model=list[ApplicationListItem])
def list_job_applicants(job_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_recruiter)):
    """Powers the 'View applicants' link on each job card in /jobPositions."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return [application_to_list_item(a) for a in job.applications]
