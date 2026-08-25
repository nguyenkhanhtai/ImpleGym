"""Pydantic request and response schemas for ImpleGym."""

from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field


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
    sample_cases: list[SampleCaseSchema] = Field(default_factory=list)
    testcases_dir: str | None = None
    time_limit: float = 2.0
    memory_limit_mb: int = 1024
    tags: list[str] = Field(default_factory=list)
    source: str = "yosupo"
    is_difficulty_customized: bool = False


class ProblemResponseSchema(ProblemBaseSchema):
    """Problem response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    is_solved: bool | None = False
    is_successful: bool | None = False
    best_time_seconds: float | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def target_time_seconds(self) -> float:
        """Target benchmark time in seconds (difficulty * 5 minutes)."""
        return float(self.difficulty * 5 * 60)


class ProblemUpdateSchema(BaseModel):
    """Schema for manually updating problem properties."""

    difficulty: int | None = Field(None, ge=1, le=10, description="Difficulty rating from 1 to 10")
    title: str | None = None
    category: str | None = None
    tags: list[str] | None = None


class ProblemFilterParams(BaseModel):
    """Filter parameters for problem search."""

    search: str | None = None
    category: str | None = None
    min_difficulty: int | None = Field(default=1, ge=1, le=10)
    max_difficulty: int | None = Field(default=10, ge=1, le=10)
    tag: str | None = None
    solved_status: str | None = Field(default="all", description="all, solved, unsolved")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class SamplerConfigSchema(BaseModel):
    """Gaussian sampler configuration schema."""

    mean_difficulty: float = Field(default=5.5, ge=1.0, le=10.0)
    standard_deviation: float = Field(
        default=1.5,
        gt=0.0,
        le=5.0,
        validation_alias=AliasChoices("standard_deviation", "std_dev"),
    )
    skewness: str = Field(
        default="balanced",
        description="Distribution skewness: 'balanced', 'left' (easier), or 'right' (harder)",
    )
    category: str | None = None
    tag: str | None = None
    exclude_solved: bool = False
    num_problems: int = Field(
        default=1, ge=1, le=14, description="Number of problems to sample (1 to 14)"
    )


class StartSessionRequest(BaseModel):
    """Start workout contest session request."""

    name: str | None = Field(
        default=None,
        description="Contest name. If omitted, defaults to Gym Contest - YYYY-MM-DD HH:MM",
    )
    problem_slug: str | None = None
    problem_slugs: list[str] | None = None
    num_problems: int = Field(
        default=1, ge=1, le=14, description="Number of problems in contest (1 to 14)"
    )
    sampler_config: SamplerConfigSchema | None = None


class SwitchProblemRequest(BaseModel):
    """Switch active problem within a contest session."""

    session_id: int | None = None
    problem_id: int | None = None
    problem_slug: str | None = None
    problem_index: int | None = None


class SubmissionCreateRequest(BaseModel):
    """Create submission request."""

    session_id: int | None = None
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
    message: str | None = None


class SubmissionResponseSchema(BaseModel):
    """Submission result schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int | None = None
    problem_id: int
    language: str
    compiler_profile: str
    compiler_flags: str
    verdict: str
    exec_time_ms: float | None = None
    memory_kb: int | None = None
    test_results: list[TestCaseResultSchema] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime


class PracticeSessionResponseSchema(BaseModel):
    """Practice contest session detail schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str = ""
    problem_id: int
    problem: ProblemResponseSchema
    problem_ids: list[int] = Field(default_factory=list)
    problems: list[ProblemResponseSchema] = Field(default_factory=list)
    current_problem_index: int = 0
    problem_statuses: dict[str, str] = Field(default_factory=dict)
    num_problems: int = 1
    solved_count: int = 0
    status: str
    is_manual_selection: bool
    started_at: datetime
    finished_at: datetime | None = None
    total_duration_seconds: float | None = None
    target_time_seconds: float | None = None
    total_target_time_seconds: float | None = None
    is_successful: bool | None = None
    submission_count: int
    submissions: list[SubmissionResponseSchema] = Field(default_factory=list)


class AIReviewSuggestion(BaseModel):
    """Structured AI review suggestion."""

    category: str  # Performance, CP Idiom, Memory Layout, Edge Case, Clean Code
    title: str
    detail: str
    code_diff: str | None = None


class AIReviewResponseSchema(BaseModel):
    """AI code review response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    submission_id: int
    feedback_markdown: str
    suggestions: list[AIReviewSuggestion] = Field(default_factory=list)
    model_used: str
    created_at: datetime


class AIConfigSchema(BaseModel):
    """Configuration schema for AI provider and hyperparameters."""

    provider: str = Field(default="openai", description="openai, gemini, deepseek, claude, ollama")
    model: str | None = Field(default=None, description="Model identifier")
    api_key: str | None = Field(default=None, description="API Key")
    api_base: str | None = Field(default=None, description="Custom API Base URL")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int | None = Field(default=4096, ge=128, le=16384, description="Max token limit")


class GenerateProblemRequest(BaseModel):
    """Request schema for GPT problem generator."""

    topic_1: str = Field(description="First DS or concept, e.g., Fenwick Tree")
    topic_2: str = Field(description="Second DS or concept, e.g., Heavy-Light Decomposition")
    target_difficulty: int = Field(default=6, ge=1, le=10)
    extra_instructions: str | None = None
    ai_config: AIConfigSchema | None = None


class CompilerProfileSchema(BaseModel):
    """Available compiler metadata."""

    id: str
    name: str
    executable: str
    language: str
    default_flags: str
    supported_standards: list[str] = Field(default_factory=list)
