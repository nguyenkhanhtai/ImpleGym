"""Practice session and stopwatch lifecycle management."""

from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from implegym.db.models import PracticeSession, Problem, Submission
from implegym.judge.runner import JudgeRunResult, JudgeRunner
from implegym.models.schemas import (
    PracticeSessionResponseSchema,
    ProblemResponseSchema,
    SubmissionCreateRequest,
    SubmissionResponseSchema,
    TestCaseResultSchema,
)


class SessionTracker:
    """Manages workout sessions, live stopwatch state, and submissions."""

    def __init__(self, session: AsyncSession, judge_runner: Optional[JudgeRunner] = None) -> None:
        self.session = session
        self.judge = judge_runner or JudgeRunner()

    async def start_session(
        self, problem_id: int, is_manual_selection: bool = False
    ) -> PracticeSessionResponseSchema:
        """Start a new workout session and start stopwatch timer."""
        # Check if there is an active session for this problem or close previous active ones
        active_stmt = (
            select(PracticeSession)
            .where(PracticeSession.status == "active")
            .options(selectinload(PracticeSession.problem), selectinload(PracticeSession.submissions))
        )
        active_res = await self.session.execute(active_stmt)
        active_sessions = active_res.scalars().all()
        for s in active_sessions:
            s.status = "abandoned"
            s.finished_at = datetime.now(timezone.utc)
            if s.started_at:
                s.total_duration_seconds = (s.finished_at - s.started_at).total_seconds()

        now = datetime.now(timezone.utc)
        new_session = PracticeSession(
            problem_id=problem_id,
            status="active",
            is_manual_selection=is_manual_selection,
            started_at=now,
            submission_count=0,
        )
        self.session.add(new_session)
        await self.session.commit()
        await self.session.refresh(new_session, ["problem", "submissions"])

        return await self._to_session_schema(new_session)

    async def get_active_session(self) -> Optional[PracticeSessionResponseSchema]:
        """Fetch the currently active session if one exists."""
        stmt = (
            select(PracticeSession)
            .where(PracticeSession.status == "active")
            .options(selectinload(PracticeSession.problem), selectinload(PracticeSession.submissions))
            .order_by(PracticeSession.id.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        active = res.scalar_one_or_none()
        if not active:
            return None
        return await self._to_session_schema(active)

    async def submit_code(
        self, req: SubmissionCreateRequest
    ) -> Tuple[SubmissionResponseSchema, Optional[PracticeSessionResponseSchema]]:
        """Submit code, judge it against test cases, and stop timer on AC."""
        # Find problem
        prob_stmt = select(Problem).where(Problem.slug == req.problem_slug)
        prob_res = await self.session.execute(prob_stmt)
        problem = prob_res.scalar_one_or_none()
        if not problem:
            raise ValueError(f"Problem '{req.problem_slug}' not found")

        # Find active session if session_id provided or inferred
        practice_session: Optional[PracticeSession] = None
        if req.session_id:
            sess_stmt = (
                select(PracticeSession)
                .where(PracticeSession.id == req.session_id)
                .options(selectinload(PracticeSession.problem), selectinload(PracticeSession.submissions))
            )
            sess_res = await self.session.execute(sess_stmt)
            practice_session = sess_res.scalar_one_or_none()

        if not practice_session:
            # Check for active session matching problem
            active_stmt = (
                select(PracticeSession)
                .where(PracticeSession.status == "active", PracticeSession.problem_id == problem.id)
                .options(selectinload(PracticeSession.problem), selectinload(PracticeSession.submissions))
                .limit(1)
            )
            active_res = await self.session.execute(active_stmt)
            practice_session = active_res.scalar_one_or_none()

        # Run Judge Evaluation
        run_res: JudgeRunResult = self.judge.evaluate(
            code=req.code,
            sample_cases=problem.sample_cases,
            time_limit_sec=problem.time_limit,
            compiler_profile=req.compiler_profile,
            compiler_flags=req.compiler_flags,
        )

        test_results_dicts = [tc.model_dump() for tc in run_res.test_results]

        submission = Submission(
            session_id=practice_session.id if practice_session else None,
            problem_id=problem.id,
            code=req.code,
            language=req.language,
            compiler_profile=req.compiler_profile,
            compiler_flags=req.compiler_flags,
            verdict=run_res.verdict,
            exec_time_ms=run_res.exec_time_ms,
            memory_kb=run_res.memory_kb,
            test_results=test_results_dicts,
            error_message=run_res.error_message,
        )
        self.session.add(submission)

        # Update session timer if AC
        if practice_session:
            practice_session.submission_count += 1
            if run_res.verdict == "AC" and practice_session.status == "active":
                practice_session.status = "ac"
                now = datetime.now(timezone.utc)
                practice_session.finished_at = now
                if practice_session.started_at:
                    practice_session.total_duration_seconds = (
                        now - practice_session.started_at
                    ).total_seconds()

        await self.session.commit()
        await self.session.refresh(submission)

        sub_schema = SubmissionResponseSchema(
            id=submission.id,
            session_id=submission.session_id,
            problem_id=submission.problem_id,
            language=submission.language,
            compiler_profile=submission.compiler_profile,
            compiler_flags=submission.compiler_flags,
            verdict=submission.verdict,
            exec_time_ms=submission.exec_time_ms,
            memory_kb=submission.memory_kb,
            test_results=[TestCaseResultSchema(**tc) for tc in submission.test_results],
            error_message=submission.error_message,
            created_at=submission.created_at,
        )

        session_schema = None
        if practice_session:
            await self.session.refresh(practice_session, ["problem", "submissions"])
            session_schema = await self._to_session_schema(practice_session)

        return sub_schema, session_schema

    async def list_session_history(self, limit: int = 50) -> List[PracticeSessionResponseSchema]:
        """List past practice sessions for history tab."""
        stmt = (
            select(PracticeSession)
            .options(selectinload(PracticeSession.problem), selectinload(PracticeSession.submissions))
            .order_by(PracticeSession.id.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        sessions = res.scalars().all()
        return [await self._to_session_schema(s) for s in sessions]

    async def _to_session_schema(
        self, practice_session: PracticeSession
    ) -> PracticeSessionResponseSchema:
        """Convert PracticeSession model to response schema."""
        prob = practice_session.problem
        prob_schema = ProblemResponseSchema.model_validate(prob)

        submissions_schema = [
            SubmissionResponseSchema(
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
            for sub in practice_session.submissions
        ]

        return PracticeSessionResponseSchema(
            id=practice_session.id,
            problem_id=practice_session.problem_id,
            problem=prob_schema,
            status=practice_session.status,
            is_manual_selection=practice_session.is_manual_selection,
            started_at=practice_session.started_at,
            finished_at=practice_session.finished_at,
            total_duration_seconds=practice_session.total_duration_seconds,
            submission_count=practice_session.submission_count,
            submissions=submissions_schema,
        )
