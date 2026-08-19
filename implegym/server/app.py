"""FastAPI server application exposing REST and WebSocket endpoints."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from implegym.ai.generator import ProblemGeneratorService
from implegym.ai.refiner import CodeRefinerService
from implegym.config import settings
from implegym.db.database import get_db_session, get_engine, init_db, session_scope
from implegym.judge.compiler import CompilerManager
from implegym.models.schemas import (
    AIReviewResponseSchema,
    CompilerProfileSchema,
    GenerateProblemRequest,
    PracticeSessionResponseSchema,
    ProblemFilterParams,
    ProblemResponseSchema,
    StartSessionRequest,
    SubmissionCreateRequest,
    SubmissionResponseSchema,
)
from implegym.problems.catalog import ProblemCatalogService
from implegym.problems.indexer import ProblemIndexer
from implegym.sampler.distribution import GaussianSampler
from implegym.session.tracker import SessionTracker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan event handler initializing database and seeding default problems."""
    await init_db()
    async with session_scope() as session:
        indexer = ProblemIndexer(session)
        await indexer.seed_default_problems()
    yield


app = FastAPI(
    title="ImpleGym API",
    description="Competitive Programming Implementation Training Gym",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

compiler_manager = CompilerManager()


@app.get("/api/health")
async def health_check() -> Dict[str, str]:
    """Healthcheck endpoint."""
    return {"status": "ok", "app": "ImpleGym"}


@app.get("/api/compilers", response_model=List[CompilerProfileSchema])
async def get_compilers() -> List[CompilerProfileSchema]:
    """List available compiler profiles detected on host."""
    return compiler_manager.get_available_profiles()


@app.get("/api/categories", response_model=List[str])
async def get_categories(
    db: AsyncSession = Depends(get_db_session),
) -> List[str]:
    """List unique problem categories."""
    catalog = ProblemCatalogService(db)
    return await catalog.get_all_categories()


@app.get("/api/problems")
async def list_problems(
    search: Optional[str] = None,
    category: Optional[str] = None,
    min_difficulty: int = Query(default=1, ge=1, le=10),
    max_difficulty: int = Query(default=10, ge=1, le=10),
    tag: Optional[str] = None,
    solved_status: str = Query(default="all", regex="^(all|solved|unsolved)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Search and filter problem catalog."""
    params = ProblemFilterParams(
        search=search,
        category=category,
        min_difficulty=min_difficulty,
        max_difficulty=max_difficulty,
        tag=tag,
        solved_status=solved_status,
        page=page,
        page_size=page_size,
    )
    catalog = ProblemCatalogService(db)
    items, total = await catalog.list_problems(params)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.get("/api/problems/{slug}", response_model=ProblemResponseSchema)
async def get_problem(
    slug: str, db: AsyncSession = Depends(get_db_session)
) -> ProblemResponseSchema:
    """Retrieve problem details by slug."""
    catalog = ProblemCatalogService(db)
    prob = await catalog.get_by_slug(slug)
    if not prob:
        raise HTTPException(status_code=404, detail="Problem not found")
    return prob


@app.post("/api/session/start", response_model=PracticeSessionResponseSchema)
async def start_session(
    req: StartSessionRequest, db: AsyncSession = Depends(get_db_session)
) -> PracticeSessionResponseSchema:
    """Start workout session via manual slug or Gaussian sampling."""
    catalog = ProblemCatalogService(db)
    target_prob: Optional[ProblemResponseSchema] = None

    if req.problem_slug:
        target_prob = await catalog.get_by_slug(req.problem_slug)
        if not target_prob:
            raise HTTPException(status_code=404, detail="Problem not found")
        is_manual = True
    elif req.sampler_config:
        sampler = GaussianSampler(db)
        target_prob = await sampler.sample_problem(req.sampler_config)
        if not target_prob:
            raise HTTPException(
                status_code=404, detail="No matching problems found for sampler configuration"
            )
        is_manual = False
    else:
        # Default sampling
        sampler = GaussianSampler(db)
        from implegym.models.schemas import SamplerConfigSchema
        target_prob = await sampler.sample_problem(SamplerConfigSchema())
        if not target_prob:
            raise HTTPException(status_code=404, detail="No problems in database")
        is_manual = False

    tracker = SessionTracker(db)
    return await tracker.start_session(target_prob.id, is_manual_selection=is_manual)


@app.get("/api/session/active", response_model=Optional[PracticeSessionResponseSchema])
async def get_active_session(
    db: AsyncSession = Depends(get_db_session),
) -> Optional[PracticeSessionResponseSchema]:
    """Get active workout session and current stopwatch status."""
    tracker = SessionTracker(db)
    return await tracker.get_active_session()


@app.post("/api/session/submit")
async def submit_code(
    req: SubmissionCreateRequest, db: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """Submit solution code, execute local judge, and stop stopwatch if AC."""
    tracker = SessionTracker(db)
    try:
        submission, session_res = await tracker.submit_code(req)
        return {
            "submission": submission,
            "session": session_res,
        }
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@app.get("/api/history/sessions", response_model=List[PracticeSessionResponseSchema])
async def list_session_history(
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
) -> List[PracticeSessionResponseSchema]:
    """List historical practice sessions and solve metrics."""
    tracker = SessionTracker(db)
    return await tracker.list_session_history(limit=limit)


@app.post("/api/submissions/{submission_id}/refine", response_model=AIReviewResponseSchema)
async def refine_submission(
    submission_id: int, db: AsyncSession = Depends(get_db_session)
) -> AIReviewResponseSchema:
    """Request AI code review with CP tips for a submission."""
    refiner = CodeRefinerService(db)
    try:
        return await refiner.refine_submission(submission_id)
    except ValueError as ex:
        raise HTTPException(status_code=404, detail=str(ex))


@app.post("/api/ai/generate", response_model=ProblemResponseSchema)
async def generate_problem(
    req: GenerateProblemRequest, db: AsyncSession = Depends(get_db_session)
) -> ProblemResponseSchema:
    """Synthesize a custom problem combining 2+ data structures with GPT."""
    generator = ProblemGeneratorService(db)
    return await generator.generate_problem(req)


# Mount static directory for frontend
static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def serve_index() -> FileResponse:
    """Serve single-page frontend application."""
    index_path = static_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend assets not found")
    return FileResponse(str(index_path))
