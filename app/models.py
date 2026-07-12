import enum
import uuid
from datetime import datetime, date

from sqlalchemy import (
    String,
    Text,
    Integer,
    Boolean,
    ForeignKey,
    DateTime,
    Date,
    Enum as SAEnum,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


UUID_PK = lambda: mapped_column(  # noqa: E731
    UUID(as_uuid=False), primary_key=True, default=gen_uuid
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class UserRole(str, enum.Enum):
    RECRUITER = "recruiter"
    CANDIDATE = "candidate"


class JobStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    DRAFT = "draft"


class EmploymentType(str, enum.Enum):
    FULL_TIME = "Full-time"
    PART_TIME = "Part-time"
    CONTRACT = "Contract"
    INTERNSHIP = "Internship"


class ApplicationStatus(str, enum.Enum):
    NEW = "new"
    UNDER_REVIEW = "under_review"
    SHORTLISTED = "shortlisted"
    INTERVIEW = "interview"
    OFFERED = "offered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class MessageSender(str, enum.Enum):
    HR = "hr"
    CANDIDATE = "candidate"
    SYSTEM = "system"


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = UUID_PK()
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole, name="user_role"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    candidate_profile: Mapped["Candidate"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    posted_jobs: Mapped[list["Job"]] = relationship(back_populates="posted_by")


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = UUID_PK()
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    department: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    employment_type: Mapped[EmploymentType] = mapped_column(
        SAEnum(EmploymentType, name="employment_type"), nullable=False
    )
    location_city: Mapped[str] = mapped_column(String(100), nullable=False)
    location_country: Mapped[str] = mapped_column(String(100), nullable=False)
    field_of_study: Mapped[str | None] = mapped_column(String(150), nullable=True)
    salary_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="job_status"), default=JobStatus.OPEN, nullable=False, index=True
    )
    posted_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    posted_by: Mapped["User | None"] = relationship(back_populates="posted_jobs")
    requirements: Mapped[list["JobRequirement"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="JobRequirement.position"
    )
    skills: Mapped[list["JobSkill"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    applications: Mapped[list["Application"]] = relationship(back_populates="job", cascade="all, delete-orphan")

    @property
    def applicant_count(self) -> int:
        return len(self.applications)


class JobRequirement(Base):
    __tablename__ = "job_requirements"

    id: Mapped[str] = UUID_PK()
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    job: Mapped["Job"] = relationship(back_populates="requirements")


class JobSkill(Base):
    __tablename__ = "job_skills"
    __table_args__ = (UniqueConstraint("job_id", "skill", name="uq_job_skill"),)

    id: Mapped[str] = UUID_PK()
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    skill: Mapped[str] = mapped_column(String(100), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    job: Mapped["Job"] = relationship(back_populates="skills")


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------
class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[str] = UUID_PK()
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True, nullable=True
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    headline: Mapped[str | None] = mapped_column(String(200), nullable=True)  # e.g. "Lead Frontend Engineer at Lumen"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User | None"] = relationship(back_populates="candidate_profile")
    skills: Mapped[list["CandidateSkill"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    experiences: Mapped[list["CandidateExperience"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", order_by="CandidateExperience.start_date.desc()"
    )
    educations: Mapped[list["CandidateEducation"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    applications: Mapped[list["Application"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def initials(self) -> str:
        parts = [self.first_name[:1], self.last_name[:1]]
        return "".join(p.upper() for p in parts if p)


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"
    __table_args__ = (UniqueConstraint("candidate_id", "skill", name="uq_candidate_skill"),)

    id: Mapped[str] = UUID_PK()
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    skill: Mapped[str] = mapped_column(String(100), nullable=False)

    candidate: Mapped["Candidate"] = relationship(back_populates="skills")


class CandidateExperience(Base):
    __tablename__ = "candidate_experiences"

    id: Mapped[str] = UUID_PK()
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    company: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    candidate: Mapped["Candidate"] = relationship(back_populates="experiences")


class CandidateEducation(Base):
    __tablename__ = "candidate_educations"

    id: Mapped[str] = UUID_PK()
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    degree: Mapped[str] = mapped_column(String(150), nullable=False)
    institution: Mapped[str] = mapped_column(String(150), nullable=False)
    graduation_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="educations")


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("job_id", "candidate_id", name="uq_job_candidate_application"),)

    id: Mapped[str] = UUID_PK()
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)

    # Snapshot fields captured directly from the "Apply for this Position" form
    portfolio_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resume_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    portfolio_file_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    professional_skills_raw: Mapped[str | None] = mapped_column(String(500), nullable=True)
    years_of_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_monthly_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_monthly_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[ApplicationStatus] = mapped_column(
        SAEnum(ApplicationStatus, name="application_status"),
        default=ApplicationStatus.NEW,
        nullable=False,
        index=True,
    )

    ai_match_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)

    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    job: Mapped["Job"] = relationship(back_populates="applications")
    candidate: Mapped["Candidate"] = relationship(back_populates="applications")
    skill_matches: Mapped[list["ApplicationSkillMatch"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    messages: Mapped[list["ApplicationMessage"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ApplicationMessage.created_at"
    )


class ApplicationSkillMatch(Base):
    __tablename__ = "application_skill_matches"

    id: Mapped[str] = UUID_PK()
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    skill: Mapped[str] = mapped_column(String(100), nullable=False)
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False)  # True = matched skill, False = missing skill

    application: Mapped["Application"] = relationship(back_populates="skill_matches")


class ApplicationMessage(Base):
    __tablename__ = "application_messages"

    id: Mapped[str] = UUID_PK()
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    sender: Mapped[MessageSender] = mapped_column(SAEnum(MessageSender, name="message_sender"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    application: Mapped["Application"] = relationship(back_populates="messages")
