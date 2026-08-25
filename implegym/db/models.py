"""SQLAlchemy ORM models for ImpleGym."""

from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator


class SQLiteCompatibleJSON(TypeDecorator):
    """JSON type that falls back to standard JSON if JSONB is unavailable."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class Base(DeclarativeBase):
    """Base declarative class."""

    pass


class Problem(Base):
    """Problem entity model."""

    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, index=True, nullable=False)  # 1 to 10
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    input_format: Mapped[str] = mapped_column(Text, nullable=False, default="")
    output_format: Mapped[str] = mapped_column(Text, nullable=False, default="")
    constraints: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sample_cases: Mapped[list[dict[str, str]]] = mapped_column(
        SQLiteCompatibleJSON, default=list, nullable=False
    )
    testcases_dir: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, default=None)
    time_limit: Mapped[float] = mapped_column(Float, default=2.0, nullable=False)
    memory_limit_mb: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    tags: Mapped[list[str]] = mapped_column(SQLiteCompatibleJSON, default=list, nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="yosupo", nullable=False)
    is_difficulty_customized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    sessions: Mapped[list["PracticeSession"]] = relationship(
        "PracticeSession", back_populates="problem"
    )
    submissions: Mapped[list["Submission"]] = relationship("Submission", back_populates="problem")


class PracticeSession(Base):
    """Practice workout contest session entity."""

    __tablename__ = "practice_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    problem_id: Mapped[int] = mapped_column(Integer, ForeignKey("problems.id"), nullable=False)
    problem_ids: Mapped[list[int]] = mapped_column(
        SQLiteCompatibleJSON, default=list, nullable=False
    )
    current_problem_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    problem_statuses: Mapped[dict[str, str]] = mapped_column(
        SQLiteCompatibleJSON, default=dict, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), default="active", nullable=False
    )  # active, ac, abandoned, stopped
    is_manual_selection: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    submission_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    problem: Mapped["Problem"] = relationship("Problem", back_populates="sessions")
    submissions: Mapped[list["Submission"]] = relationship("Submission", back_populates="session")


class Submission(Base):
    """Submission entity record."""

    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("practice_sessions.id"), nullable=True, index=True
    )
    problem_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("problems.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(32), default="cpp", nullable=False)
    compiler_profile: Mapped[str] = mapped_column(String(64), default="g++ (C++20)", nullable=False)
    compiler_flags: Mapped[str] = mapped_column(String(256), default="-O3", nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), default="JUDGING", nullable=False, index=True)
    exec_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_kb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    test_results: Mapped[list[dict[str, Any]]] = mapped_column(
        SQLiteCompatibleJSON, default=list, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    problem: Mapped["Problem"] = relationship("Problem", back_populates="submissions")
    session: Mapped[Optional["PracticeSession"]] = relationship(
        "PracticeSession", back_populates="submissions"
    )
    ai_review: Mapped[Optional["AIReview"]] = relationship(
        "AIReview", back_populates="submission", uselist=False, cascade="all, delete-orphan"
    )


class AIReview(Base):
    """AI code refinement review record."""

    __tablename__ = "ai_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("submissions.id"), unique=True, nullable=False
    )
    feedback_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    suggestions: Mapped[list[dict[str, Any]]] = mapped_column(
        SQLiteCompatibleJSON, default=list, nullable=False
    )
    model_used: Mapped[str] = mapped_column(String(64), default="gpt-4o", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    submission: Mapped["Submission"] = relationship("Submission", back_populates="ai_review")


class CustomProblem(Base):
    """Generated custom composite problem metadata."""

    __tablename__ = "custom_problems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    prompt_context: Mapped[str] = mapped_column(Text, nullable=False)
    solution_cpp: Mapped[str] = mapped_column(Text, nullable=False)
    generator_cpp: Mapped[str] = mapped_column(Text, nullable=False)
    checker_cpp: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
