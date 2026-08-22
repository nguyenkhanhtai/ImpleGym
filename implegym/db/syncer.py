"""Database synchronization and migration service between SQLite and PostgreSQL."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from implegym.db.models import AIReview, Base, CustomProblem, PracticeSession, Problem, Submission

logger = logging.getLogger("implegym.db.syncer")


class DatabaseSyncService:
    """Service to bidirectional sync or migrate problems, sessions, and submissions between DB engines."""

    def __init__(
        self,
        source_url: str,
        target_url: str,
    ) -> None:
        self.source_url = source_url
        self.target_url = target_url

    def _create_engine(self, url: str) -> AsyncEngine:
        connect_args = {}
        if "sqlite" in url:
            connect_args = {"check_same_thread": False}
        return create_async_engine(url, echo=False, future=True, connect_args=connect_args)

    async def sync_data(self) -> dict[str, Any]:
        """Perform full sync from source database to target database."""
        source_engine = self._create_engine(self.source_url)
        target_engine = self._create_engine(self.target_url)

        # 1. Initialize schema in both Source and Target DB to guarantee tables exist
        async with source_engine.begin() as src_conn:
            await src_conn.run_sync(Base.metadata.create_all)

        async with target_engine.begin() as tgt_conn:
            await tgt_conn.run_sync(Base.metadata.create_all)

        source_factory = async_sessionmaker(
            source_engine, expire_on_commit=False, class_=AsyncSession
        )
        target_factory = async_sessionmaker(
            target_engine, expire_on_commit=False, class_=AsyncSession
        )

        stats = {
            "problems_synced": 0,
            "sessions_synced": 0,
            "submissions_synced": 0,
            "ai_reviews_synced": 0,
            "custom_problems_synced": 0,
        }

        async with source_factory() as src_session, target_factory() as tgt_session:
            # 1. Sync Problems
            problems_res = await src_session.execute(select(Problem))
            src_problems = problems_res.scalars().all()
            for p in src_problems:
                existing = await tgt_session.execute(select(Problem).where(Problem.slug == p.slug))
                if not existing.scalar_one_or_none():
                    new_p = Problem(
                        slug=p.slug,
                        title=p.title,
                        category=p.category,
                        difficulty=p.difficulty,
                        statement=p.statement,
                        input_format=p.input_format,
                        output_format=p.output_format,
                        constraints=p.constraints,
                        sample_cases=p.sample_cases,
                        time_limit=p.time_limit,
                        memory_limit_mb=p.memory_limit_mb,
                        tags=p.tags,
                        source=p.source,
                    )
                    tgt_session.add(new_p)
                    stats["problems_synced"] += 1

            # 2. Sync Custom Problems
            custom_res = await src_session.execute(select(CustomProblem))
            src_custom = custom_res.scalars().all()
            for cp in src_custom:
                existing = await tgt_session.execute(
                    select(CustomProblem).where(CustomProblem.slug == cp.slug)
                )
                if not existing.scalar_one_or_none():
                    new_cp = CustomProblem(
                        slug=cp.slug,
                        title=cp.title,
                        prompt_context=cp.prompt_context,
                        solution_cpp=cp.solution_cpp,
                        generator_cpp=cp.generator_cpp,
                        checker_cpp=cp.checker_cpp,
                    )
                    tgt_session.add(new_cp)
                    stats["custom_problems_synced"] += 1

            # 3. Sync Practice Sessions
            sessions_res = await src_session.execute(select(PracticeSession))
            src_sessions = sessions_res.scalars().all()
            for s in src_sessions:
                existing = await tgt_session.execute(
                    select(PracticeSession).where(PracticeSession.id == s.id)
                )
                if not existing.scalar_one_or_none():
                    new_s = PracticeSession(
                        id=s.id,
                        problem_slug=s.problem_slug,
                        sampler_mode=s.sampler_mode,
                        target_difficulty=s.target_difficulty,
                        status=s.status,
                        started_at=s.started_at,
                        completed_at=s.completed_at,
                        total_duration_seconds=s.total_duration_seconds,
                        total_attempts=s.total_attempts,
                    )
                    tgt_session.add(new_s)
                    stats["sessions_synced"] += 1

            # 4. Sync Submissions
            sub_res = await src_session.execute(select(Submission))
            src_subs = sub_res.scalars().all()
            for sub in src_subs:
                existing = await tgt_session.execute(
                    select(Submission).where(Submission.id == sub.id)
                )
                if not existing.scalar_one_or_none():
                    new_sub = Submission(
                        id=sub.id,
                        session_id=sub.session_id,
                        problem_slug=sub.problem_slug,
                        compiler_profile=sub.compiler_profile,
                        compiler_flags=sub.compiler_flags,
                        code=sub.code,
                        verdict=sub.verdict,
                        execution_time_ms=sub.execution_time_ms,
                        memory_used_kb=sub.memory_used_kb,
                        compile_output=sub.compile_output,
                        testcase_results=sub.testcase_results,
                        submitted_at=sub.submitted_at,
                    )
                    tgt_session.add(new_sub)
                    stats["submissions_synced"] += 1

            # 5. Sync AI Reviews
            ai_res = await src_session.execute(select(AIReview))
            src_ai = ai_res.scalars().all()
            for r in src_ai:
                existing = await tgt_session.execute(select(AIReview).where(AIReview.id == r.id))
                if not existing.scalar_one_or_none():
                    new_r = AIReview(
                        id=r.id,
                        submission_id=r.submission_id,
                        model_used=r.model_used,
                        critique=r.critique,
                        suggestions=r.suggestions,
                        refined_code=r.refined_code,
                        created_at=r.created_at,
                    )
                    tgt_session.add(new_r)
                    stats["ai_reviews_synced"] += 1

            await tgt_session.commit()

        await source_engine.dispose()
        await target_engine.dispose()
        return stats
