from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user, require_recruiter
from app.models import Candidate, CandidateSkill, CandidateExperience, CandidateEducation, User, UserRole
from app.schemas import (
    CandidateOut,
    CandidateUpdate,
    ExperienceIn,
    ExperienceOut,
    EducationIn,
    EducationOut,
)

router = APIRouter(prefix="/api/candidates", tags=["Candidates"])


def _get_candidate_or_404(db: Session, candidate_id: str) -> Candidate:
    candidate = (
        db.query(Candidate)
        .options(
            joinedload(Candidate.skills),
            joinedload(Candidate.experiences),
            joinedload(Candidate.educations),
        )
        .filter(Candidate.id == candidate_id)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return candidate


def _authorize_profile_edit(candidate: Candidate, current_user: User):
    is_owner = candidate.user_id == current_user.id
    is_recruiter = current_user.role == UserRole.RECRUITER
    if not (is_owner or is_recruiter):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to edit this profile")


@router.get("/{candidate_id}", response_model=CandidateOut)
def get_candidate(
    candidate_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Powers the candidate-details page's profile, skills, experience, and education sections."""
    candidate = _get_candidate_or_404(db, candidate_id)
    if current_user.role != UserRole.RECRUITER and candidate.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this profile")
    return candidate


@router.put("/{candidate_id}", response_model=CandidateOut)
def update_candidate(
    candidate_id: str,
    payload: CandidateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidate = _get_candidate_or_404(db, candidate_id)
    _authorize_profile_edit(candidate, current_user)

    update_data = payload.model_dump(exclude_unset=True, exclude={"skills"})
    for field, value in update_data.items():
        setattr(candidate, field, value)

    if payload.skills is not None:
        db.query(CandidateSkill).filter(CandidateSkill.candidate_id == candidate.id).delete()
        for skill in dict.fromkeys(s.strip() for s in payload.skills if s.strip()):
            db.add(CandidateSkill(candidate_id=candidate.id, skill=skill))

    db.commit()
    # ✨ التعديل هنا: إعادة جلب الكانديديت بالعلاقات المحدثة بدلاً من refresh العادية
    return _get_candidate_or_404(db, candidate_id)


@router.post("/{candidate_id}/experiences", response_model=ExperienceOut, status_code=status.HTTP_201_CREATED)
def add_experience(
    candidate_id: str,
    payload: ExperienceIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidate = _get_candidate_or_404(db, candidate_id)
    _authorize_profile_edit(candidate, current_user)

    experience = CandidateExperience(candidate_id=candidate.id, **payload.model_dump())
    db.add(experience)
    db.commit()
    db.refresh(experience)
    return experience


@router.put("/{candidate_id}/experiences/{experience_id}", response_model=ExperienceOut)
def update_experience(
    candidate_id: str,
    experience_id: str,
    payload: ExperienceIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidate = _get_candidate_or_404(db, candidate_id)
    _authorize_profile_edit(candidate, current_user)

    experience = db.get(CandidateExperience, experience_id)
    if not experience or experience.candidate_id != candidate.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experience entry not found")

    for field, value in payload.model_dump().items():
        setattr(experience, field, value)
    db.commit()
    db.refresh(experience)
    return experience


@router.delete("/{candidate_id}/experiences/{experience_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_experience(
    candidate_id: str,
    experience_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidate = _get_candidate_or_404(db, candidate_id)
    _authorize_profile_edit(candidate, current_user)

    experience = db.get(CandidateExperience, experience_id)
    if not experience or experience.candidate_id != candidate.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experience entry not found")
    db.delete(experience)
    db.commit()


@router.post("/{candidate_id}/educations", response_model=EducationOut, status_code=status.HTTP_201_CREATED)
def add_education(
    candidate_id: str,
    payload: EducationIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidate = _get_candidate_or_404(db, candidate_id)
    _authorize_profile_edit(candidate, current_user)

    education = CandidateEducation(candidate_id=candidate.id, **payload.model_dump())
    db.add(education)
    db.commit()
    db.refresh(education)
    return education


@router.put("/{candidate_id}/educations/{education_id}", response_model=EducationOut)
def update_education(
    candidate_id: str,
    education_id: str,
    payload: EducationIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidate = _get_candidate_or_404(db, candidate_id)
    _authorize_profile_edit(candidate, current_user)

    education = db.get(CandidateEducation, education_id)
    if not education or education.candidate_id != candidate.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Education entry not found")

    for field, value in payload.model_dump().items():
        setattr(education, field, value)
    db.commit()
    db.refresh(education)
    return education


@router.delete("/{candidate_id}/educations/{education_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_education(
    candidate_id: str,
    education_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidate = _get_candidate_or_404(db, candidate_id)
    _authorize_profile_edit(candidate, current_user)

    education = db.get(CandidateEducation, education_id)
    if not education or education.candidate_id != candidate.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Education entry not found")
    db.delete(education)
    db.commit()
