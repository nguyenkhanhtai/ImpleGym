"""FastAPI server application exposing REST and WebSocket endpoints."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional
from fastapi import Body, Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from implegym.ai.generator import ProblemGeneratorService
from implegym.ai.refiner import CodeRefinerService
from implegym.config import settings
from implegym.db.database import get_db_session, get_engine, init_db, session_scope
from implegym.db.models import PracticeSession, Problem, Submission
from implegym.judge.compiler import CompilerManager
from implegym.models.schemas import (
    AIConfigSchema,
    AIReviewResponseSchema,
    CompilerProfileSchema,
    GenerateProblemRequest,
    PracticeSessionResponseSchema,
    ProblemFilterParams,
    ProblemResponseSchema,
    ProblemUpdateSchema,
    SamplerConfigSchema,
    StartSessionRequest,
    SubmissionCreateRequest,
    SubmissionResponseSchema,
    TestCaseResultSchema,
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
    solved_status: str = Query(default="all", pattern="^(all|successful|solved|unsolved)$"),
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
    total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 0
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@app.post("/api/problems/sync")
async def sync_yosupo_problems(
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Trigger synchronization from official yosupo06/library-checker-problems repository."""
    from implegym.problems.yosupo_syncer import YosupoSyncer
    syncer = YosupoSyncer(db)
    count = await syncer.sync_all_problems()
    return {"status": "ok", "synced_count": count}


@app.post("/api/problems/{slug}/sync")
@app.post("/api/problems/{slug}/generate-tests")
async def sync_single_yosupo_problem(
    slug: str,
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Trigger testcase generation and synchronization for a single problem by slug."""
    from implegym.problems.yosupo_syncer import YosupoSyncer
    syncer = YosupoSyncer(db)
    prob_data = await syncer.sync_problem(slug)
    if not prob_data:
        raise HTTPException(status_code=404, detail="Problem not found in repository")
    return {
        "status": "ok",
        "slug": slug,
        "testcases_count": len(prob_data.get("sample_cases", [])),
        "testcases": prob_data.get("sample_cases", []),
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


@app.patch("/api/problems/{slug}", response_model=ProblemResponseSchema)
async def update_problem(
    slug: str,
    update_req: ProblemUpdateSchema,
    db: AsyncSession = Depends(get_db_session),
) -> ProblemResponseSchema:
    """Manually update problem difficulty rating or metadata."""
    catalog = ProblemCatalogService(db)
    updated = await catalog.update_problem(slug, update_req.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Problem not found")
    return updated


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
        target_prob = await sampler.sample_problem(SamplerConfigSchema())
        if not target_prob:
            raise HTTPException(status_code=404, detail="No problems in database")
        is_manual = False

    tracker = SessionTracker(db)
    return await tracker.start_session(target_prob.id, is_manual_selection=is_manual)


@app.post("/api/sampler/sample", response_model=ProblemResponseSchema)
async def sample_problem_endpoint(
    config: SamplerConfigSchema = Body(default_factory=SamplerConfigSchema),
    db: AsyncSession = Depends(get_db_session),
) -> ProblemResponseSchema:
    """Sample a problem matching configuration filters without immediately creating a session."""
    sampler = GaussianSampler(db)
    prob = await sampler.sample_problem(config)
    if not prob:
        raise HTTPException(
            status_code=404, detail="No problems found matching sampling criteria"
        )
    return prob


@app.get("/api/session/active", response_model=Optional[PracticeSessionResponseSchema])
async def get_active_session(
    db: AsyncSession = Depends(get_db_session),
) -> Optional[PracticeSessionResponseSchema]:
    """Get active workout session and current stopwatch status."""
    tracker = SessionTracker(db)
    return await tracker.get_active_session()


@app.post("/api/session/stop", response_model=Optional[PracticeSessionResponseSchema])
async def stop_session(
    session_id: Optional[int] = None, db: AsyncSession = Depends(get_db_session)
) -> Optional[PracticeSessionResponseSchema]:
    """Manually stop the active workout stopwatch session."""
    tracker = SessionTracker(db)
    return await tracker.stop_session(session_id)


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


@app.get("/api/submissions/{submission_id}", response_model=SubmissionResponseSchema)
async def get_submission(
    submission_id: int, db: AsyncSession = Depends(get_db_session)
) -> SubmissionResponseSchema:
    """Retrieve a specific submission by ID."""
    stmt = select(Submission).where(Submission.id == submission_id)
    res = await db.execute(stmt)
    sub = res.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail=f"Submission {submission_id} not found")
    return SubmissionResponseSchema(
        id=sub.id,
        session_id=sub.session_id,
        problem_id=sub.problem_id,
        language=sub.language,
        compiler_profile=sub.compiler_profile,
        compiler_flags=sub.compiler_flags,
        verdict=sub.verdict,
        exec_time_ms=sub.exec_time_ms,
        memory_kb=sub.memory_kb,
        test_results=[TestCaseResultSchema(**tc) for tc in sub.test_results],
        error_message=sub.error_message,
        created_at=sub.created_at,
    )


@app.delete("/api/submissions/{submission_id}")
async def delete_submission(
    submission_id: int, db: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """Delete a specific submission record and its associated AI review."""
    stmt = select(Submission).where(Submission.id == submission_id)
    res = await db.execute(stmt)
    sub = res.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail=f"Submission {submission_id} not found")

    await db.delete(sub)
    await db.commit()
    return {"status": "deleted", "id": submission_id}


@app.delete("/api/history/sessions/{session_id}")
async def delete_session(
    session_id: int, db: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """Delete a practice session and all its submissions."""
    stmt = select(PracticeSession).where(PracticeSession.id == session_id)
    res = await db.execute(stmt)
    sess = res.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    await db.delete(sess)
    await db.commit()
    return {"status": "deleted", "id": session_id}


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


@app.get("/api/ai/providers")
async def list_ai_providers() -> List[Dict[str, Any]]:
    """List all supported and configured AI providers (OpenAI, Gemini, DeepSeek, Claude, Ollama)."""
    from implegym.ai.client import LLMManager
    manager = LLMManager.get_instance()
    return manager.list_available_providers()


@app.get("/api/ai/models")
async def list_ai_models(provider: Optional[str] = None) -> Dict[str, Any]:
    """Get list of available models for a specific provider or active provider."""
    from implegym.ai.client import LLMManager
    manager = LLMManager.get_instance()
    target = provider or manager.default_provider_name
    return {
        "provider": target,
        "models": manager.get_models_for_provider(target),
    }


@app.get("/api/ai/config")
async def get_ai_config() -> Dict[str, Any]:
    """Get active AI provider configuration and hyperparameters."""
    from implegym.ai.client import LLMManager
    manager = LLMManager.get_instance()
    return manager.get_current_config()


@app.post("/api/ai/config")
async def update_ai_config(config: AIConfigSchema) -> Dict[str, Any]:
    """Update runtime AI provider, API key, base URL, model, and hyperparameters."""
    from implegym.ai.client import LLMManager
    manager = LLMManager.get_instance()
    manager.configure_provider(config)
    return {
        "status": "ok",
        "message": f"Successfully updated AI provider to {config.provider}",
        "config": manager.get_current_config(),
    }


@app.post("/api/ai/generate", response_model=ProblemResponseSchema)
async def generate_problem(
    req: GenerateProblemRequest, db: AsyncSession = Depends(get_db_session)
) -> ProblemResponseSchema:
    """Synthesize a custom problem combining 2+ data structures with GPT/Gemini/DeepSeek/Claude/Ollama."""
    generator = ProblemGeneratorService(db)
    return await generator.generate_problem(req)


@app.post("/api/db/sync")
async def trigger_db_sync(
    source_url: str = "sqlite+aiosqlite:///data/implegym.db",
    target_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Sync data between SQLite and PostgreSQL databases."""
    from implegym.db.syncer import DatabaseSyncService
    tgt = target_url or settings.database_url
    syncer = DatabaseSyncService(source_url=source_url, target_url=tgt)
    return await syncer.sync_data()


# Mount static directory for frontend
static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
@app.get("/explorer")
async def serve_explorer() -> FileResponse:
    """Serve Problem Explorer page."""
    path = static_dir / "explorer.html"
    if not path.exists():
        path = static_dir / "index.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Frontend assets not found")
    return FileResponse(str(path))


@app.get("/gym")
async def serve_gym() -> FileResponse:
    """Serve Gym Workout & Stopwatch page."""
    path = static_dir / "gym.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Gym page not found")
    return FileResponse(str(path))


@app.get("/history")
async def serve_history() -> FileResponse:
    """Serve Practice Session Records & History page."""
    path = static_dir / "history.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="History page not found")
    return FileResponse(str(path))


@app.get("/forge")
async def serve_forge() -> FileResponse:
    """Serve AI Problem Forge page."""
    path = static_dir / "forge.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Forge page not found")
    return FileResponse(str(path))

