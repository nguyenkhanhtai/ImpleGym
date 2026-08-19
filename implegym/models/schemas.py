"""Pydantic request and response schemas for ImpleGym."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class SampleCaseSchema(BaseModel):
    """Sample test case schema."""

    input: str
    output: str


class ProblemBaseSchema(BaseModel):
    """Base problem schema."""

    slug: str
    title: str
    category: str
    difficulty: int = Field(ge=1, le=10, description="Difficulty rating from 1 to 10")
    statement: str
    input_format: str = ""
    output_format: str = ""
    constraints: str = ""
    sample_cases: List[SampleCaseSchema] = Field(default_factory=list)
    time_limit: float = 2.0
    memory_limit_mb: int = 1024
    tags: List[str] = Field(default_factory=list)
    source: str = "yosupo"


class ProblemResponseSchema(ProblemBaseSchema):
    """Problem response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    is_solved: Optional[bool] = False
    best_time_seconds: Optional[float] = None


class ProblemFilterParams(BaseModel):
    """Filter parameters for problem search."""

    search: Optional[str] = None
    category: Optional[str] = None
    min_difficulty: Optional[int] = Field(default=1, ge=1, le=10)
    max_difficulty: Optional[int] = Field(default=10, ge=1, le=10)
    tag: Optional[str] = None
    solved_status: Optional[str] = Field(default="all", description="all, solved, unsolved")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class SamplerConfigSchema(BaseModel):
    """Gaussian sampler configuration schema."""

    mean_difficulty: float = Field(default=5.5, ge=1.0, le=10.0)
    standard_deviation: float = Field(default=1.5, gt=0.0, le=5.0)
    skewness: str = Field(
        default="balanced",
        description="Distribution skewness: 'balanced', 'left' (easier), or 'right' (harder)",
    )
    category: Optional[str] = None
    tag: Optional[str] = None
    exclude_solved: bool = False


class StartSessionRequest(BaseModel):
    """Start workout session request."""

    problem_slug: Optional[str] = None
    sampler_config: Optional[SamplerConfigSchema] = None


class SubmissionCreateRequest(BaseModel):
    """Create submission request."""

    session_id: Optional[int] = None
    problem_slug: str
    code: str
    language: str = "cpp"
    compiler_profile: str = "g++ (C++20)"
    compiler_flags: str = "-O3"


class TestCaseResultSchema(BaseModel):
    """Single testcase execution result."""

    name: str
    verdict: str  # AC, WA, TLE, MLE, RE
    time_ms: float
    memory_kb: int
    message: Optional[str] = None


class SubmissionResponseSchema(BaseModel):
    """Submission result schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: Optional[int] = None
    problem_id: int
    language: str
    compiler_profile: str
    compiler_flags: str
    verdict: str
    exec_time_ms: Optional[float] = None
    memory_kb: Optional[int] = None
    test_results: List[TestCaseResultSchema] = Field(default_factory=list)
    error_message: Optional[str] = None
    created_at: datetime


class PracticeSessionResponseSchema(BaseModel):
    """Practice session detail schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    problem_id: int
    problem: ProblemResponseSchema
    status: str
    is_manual_selection: bool
    started_at: datetime
    finished_at: Optional[datetime] = None
    total_duration_seconds: Optional[float] = None
    submission_count: int
    submissions: List[SubmissionResponseSchema] = Field(default_factory=list)


class AIReviewSuggestion(BaseModel):
    """Structured AI review suggestion."""

    category: str  # Performance, CP Idiom, Memory Layout, Edge Case, Clean Code
    title: str
    detail: str
    code_diff: Optional[str] = None


class AIReviewResponseSchema(BaseModel):
    """AI code review response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    submission_id: int
    feedback_markdown: str
    suggestions: List[AIReviewSuggestion] = Field(default_factory=list)
    model_used: str
    created_at: datetime


class GenerateProblemRequest(BaseModel):
    """Request schema for GPT problem generator."""

    topic_1: str = Field(description="First DS or concept, e.g., Fenwick Tree")
    topic_2: str = Field(description="Second DS or concept, e.g., Heavy-Light Decomposition")
    target_difficulty: int = Field(default=6, ge=1, le=10)
    extra_instructions: Optional[str] = None


class CompilerProfileSchema(BaseModel):
    """Available compiler metadata."""

    id: str
    name: str
    executable: str
    language: str
    default_flags: str
    supported_standards: List[str] = Field(default_factory=list)
