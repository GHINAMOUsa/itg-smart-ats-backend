from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator

from app.models import UserRole, JobStatus, EmploymentType, ApplicationStatus, MessageSender


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------
class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Auth / Users
# ---------------------------------------------------------------------------
class UserSignup(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.CANDIDATE

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v, info):
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Passwords do not match")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORMModel):
    id: str
    full_name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
class JobRequirementIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class JobRequirementOut(ORMModel):
    id: str
    text: str
    position: int


class JobSkillIn(BaseModel):
    skill: str = Field(min_length=1, max_length=100)
    is_required: bool = True


class JobSkillOut(ORMModel):
    id: str
    skill: str
    is_required: bool


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    department: str = Field(min_length=1, max_length=100)
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    location_city: str = Field(min_length=1, max_length=100)
    location_country: str = Field(min_length=1, max_length=100)
    field_of_study: Optional[str] = Field(default=None, max_length=150)
    salary_range: Optional[str] = Field(default=None, max_length=100)
    summary: str = Field(min_length=1)
    description: Optional[str] = None
    status: JobStatus = JobStatus.OPEN
    requirements: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class JobUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    department: Optional[str] = Field(default=None, max_length=100)
    employment_type: Optional[EmploymentType] = None
    location_city: Optional[str] = Field(default=None, max_length=100)
    location_country: Optional[str] = Field(default=None, max_length=100)
    field_of_study: Optional[str] = Field(default=None, max_length=150)
    salary_range: Optional[str] = Field(default=None, max_length=100)
    summary: Optional[str] = None
    description: Optional[str] = None
    status: Optional[JobStatus] = None
    requirements: Optional[list[str]] = None
    skills: Optional[list[str]] = None


class JobOut(ORMModel):
    id: str
    title: str
    department: str
    employment_type: EmploymentType
    location_city: str
    location_country: str
    field_of_study: Optional[str]
    salary_range: Optional[str]
    summary: str
    description: Optional[str]
    status: JobStatus
    applicant_count: int
    created_at: datetime
    updated_at: datetime
    requirements: list[JobRequirementOut] = []
    skills: list[JobSkillOut] = []


class JobListItem(ORMModel):
    """Slim representation used for list views (dashboard cards, job board)."""

    id: str
    title: str
    department: str
    employment_type: EmploymentType
    location_city: str
    location_country: str
    salary_range: Optional[str]
    summary: str
    status: JobStatus
    applicant_count: int
    skills: list[JobSkillOut] = []


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------
class CandidateSkillOut(ORMModel):
    id: str
    skill: str


class ExperienceIn(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    company: str = Field(min_length=1, max_length=150)
    description: Optional[str] = None
    start_date: date
    end_date: Optional[date] = None
    is_current: bool = False


class ExperienceOut(ORMModel):
    id: str
    title: str
    company: str
    description: Optional[str]
    start_date: date
    end_date: Optional[date]
    is_current: bool


class EducationIn(BaseModel):
    degree: str = Field(min_length=1, max_length=150)
    institution: str = Field(min_length=1, max_length=150)
    graduation_year: Optional[int] = None


class EducationOut(ORMModel):
    id: str
    degree: str
    institution: str
    graduation_year: Optional[int]


class CandidateUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=30)
    address: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=100)
    country: Optional[str] = Field(default=None, max_length=100)
    headline: Optional[str] = Field(default=None, max_length=200)
    skills: Optional[list[str]] = None


class CandidateOut(ORMModel):
    id: str
    first_name: str
    last_name: str
    full_name: str
    initials: str
    email: EmailStr
    phone: Optional[str]
    address: Optional[str]
    city: Optional[str]
    country: Optional[str]
    headline: Optional[str]
    created_at: datetime
    skills: list[CandidateSkillOut] = []
    experiences: list[ExperienceOut] = []
    educations: list[EducationOut] = []


class CandidateListItem(ORMModel):
    """Slim representation for embedding in application list rows."""

    id: str
    full_name: str
    initials: str
    city: Optional[str]
    country: Optional[str]


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
class ApplicationCreate(BaseModel):
    """Matches the 'Apply for this Position' form on /job/jobDetails."""

    job_id: str
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    address: str = Field(min_length=1, max_length=255)
    country: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=1, max_length=30)
    professional_skills: str = Field(min_length=1, max_length=500)
    portfolio_link: Optional[str] = Field(default=None, max_length=500)
    years_of_experience: int = Field(ge=0)
    current_monthly_salary: int = Field(ge=0)
    expected_monthly_salary: int = Field(ge=0)
    # Obtain these by uploading files first via POST /api/uploads/resume and
    # POST /api/uploads/portfolio, then pass the returned URLs here.
    resume_url: str = Field(min_length=1, max_length=500)
    portfolio_file_url: Optional[str] = Field(default=None, max_length=500)


class ApplicationSkillMatchOut(ORMModel):
    skill: str
    matched: bool


class ApplicationMessageIn(BaseModel):
    message: str = Field(min_length=1)
    sender: MessageSender = MessageSender.HR


class ApplicationMessageOut(ORMModel):
    id: str
    sender: MessageSender
    message: str
    created_at: datetime


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus


class ApplicationDecision(BaseModel):
    decision: ApplicationStatus = Field(description="Must be ACCEPTED or REJECTED")

    @field_validator("decision")
    @classmethod
    def only_terminal_decisions(cls, v: ApplicationStatus):
        if v not in (ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED):
            raise ValueError("decision must be 'accepted' or 'rejected'")
        return v


class JobBrief(ORMModel):
    id: str
    title: str
    department: str


class ApplicationListItem(ORMModel):
    """Row shape for the recruiter Applicants/Dashboard table."""

    id: str
    candidate: CandidateListItem
    job: JobBrief
    ai_match_score: Optional[int]
    status: ApplicationStatus
    applied_at: datetime


class ApplicationDetail(ORMModel):
    """Full bundle for the candidate-details page."""

    id: str
    candidate: CandidateOut
    job: JobBrief
    resume_url: Optional[str]
    portfolio_file_url: Optional[str]
    portfolio_link: Optional[str]
    years_of_experience: Optional[int]
    current_monthly_salary: Optional[int]
    expected_monthly_salary: Optional[int]
    status: ApplicationStatus
    ai_match_score: Optional[int]
    ai_recommendation: Optional[str]
    skill_matches: list[ApplicationSkillMatchOut] = []
    applied_at: datetime
    decided_at: Optional[datetime]


class MyApplicationOut(ORMModel):
    """Row shape for the candidate 'My Applications' page."""

    id: str
    job: JobBrief
    status: ApplicationStatus
    ai_match_score: Optional[int]
    applied_at: datetime
    messages: list[ApplicationMessageOut] = []


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------
class UploadOut(BaseModel):
    url: str
    filename: str
