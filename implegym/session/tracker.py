"""Practice session and stopwatch lifecycle management."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from implegym.db.models import PracticeSession, Problem, Submission
from implegym.judge.runner import JudgeRunner, JudgeRunResult
from implegym.models.schemas import (
    PracticeSessionResponseSchema,
    ProblemResponseSchema,
    SubmissionCreateRequest,
    SubmissionResponseSchema,
    TestCaseResultSchema,
)


def _to_utc(dt: datetime | None) -> datetime | None:
    """Ensure datetime is offset-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class SessionTracker:
    """Manages workout contest sessions, live stopwatch state, and submissions."""

    def __init__(self, session: AsyncSession, judge_runner: JudgeRunner | None = None) -> None:
        self.session = session
        self.judge = judge_runner or JudgeRunner()

    async def start_session(
        self,
        problem_id: int | None = None,
        problem_ids: list[int] | None = None,
        name: str | None = None,
        is_manual_selection: bool = False,
    ) -> PracticeSessionResponseSchema:
        """Start a new workout contest session and start stopwatch timer."""
        # Check if there is an active session or close previous active ones
        active_stmt = (
            select(PracticeSession)
            .where(PracticeSession.status == "active")
            .options(
                selectinload(PracticeSession.problem), selectinload(PracticeSession.submissions)
            )
        )
        active_res = await self.session.execute(active_stmt)
        active_sessions = active_res.scalars().all()
        for s in active_sessions:
            s.status = "abandoned"
            s.finished_at = datetime.now(UTC)
            if s.started_at:
                s.total_duration_seconds = (
                    _to_utc(s.finished_at) - _to_utc(s.started_at)
                ).total_seconds()

        now = datetime.now(UTC)
        resolved_problem_ids: list[int] = []
        if problem_ids:
            resolved_problem_ids = list(problem_ids)
        elif problem_id:
            resolved_problem_ids = [problem_id]
        else:
            raise ValueError("Must provide at least one problem for session")

        # Clamp max problems to 14
        resolved_problem_ids = resolved_problem_ids[:14]
        primary_problem_id = resolved_problem_ids[0]

        # Contest name default: Gym Contest - YYYY-MM-DD HH:MM
        contest_name = (name or "").strip()
        if not contest_name:
            contest_name = f"Gym Contest - {now.strftime('%Y-%m-%d %H:%M')}"

        initial_statuses = {str(pid): "unsolved" for pid in resolved_problem_ids}

        new_session = PracticeSession(
            name=contest_name,
            problem_id=primary_problem_id,
            problem_ids=resolved_problem_ids,
            current_problem_index=0,
            problem_statuses=initial_statuses,
            status="active",
            is_manual_selection=is_manual_selection,
            started_at=now,
            submission_count=0,
        )
        self.session.add(new_session)
        await self.session.commit()
        await self.session.refresh(new_session, ["problem", "submissions"])

        return await self._to_session_schema(new_session)

    async def switch_session_problem(
        self,
        session_id: int | None = None,
        problem_id: int | None = None,
        problem_slug: str | None = None,
        problem_index: int | None = None,
    ) -> PracticeSessionResponseSchema:
        """Switch currently active problem within an active workout contest session."""
        stmt = select(PracticeSession).options(
            selectinload(PracticeSession.problem), selectinload(PracticeSession.submissions)
        )
        if session_id:
            stmt = stmt.where(PracticeSession.id == session_id)
        else:
            stmt = (
                stmt.where(PracticeSession.status == "active")
                .order_by(PracticeSession.id.desc())
                .limit(1)
            )

        res = await self.session.execute(stmt)
        active_sess = res.scalar_one_or_none()
        if not active_sess:
            raise ValueError("No active workout session found to switch problem")

        target_pid = problem_id
        if problem_slug and not target_pid:
            prob_res = await self.session.execute(
                select(Problem.id).where(Problem.slug == problem_slug)
            )
            target_pid = prob_res.scalar_one_or_none()

        problem_ids = active_sess.problem_ids or [active_sess.problem_id]
        if problem_index is not None and 0 <= problem_index < len(problem_ids):
            target_pid = problem_ids[problem_index]
            active_sess.current_problem_index = problem_index
        elif target_pid and target_pid in problem_ids:
            active_sess.current_problem_index = problem_ids.index(target_pid)
        elif target_pid:
            # Add to problem ids if not present (up to 14)
            if len(problem_ids) < 14:
                problem_ids.append(target_pid)
                active_sess.problem_ids = list(problem_ids)
                active_sess.current_problem_index = len(problem_ids) - 1

        if target_pid:
            active_sess.problem_id = target_pid

        await self.session.commit()
        await self.session.refresh(active_sess, ["problem", "submissions"])
        return await self._to_session_schema(active_sess)

    async def get_active_session(self) -> PracticeSessionResponseSchema | None:
        """Fetch the currently active session if one exists."""
        stmt = (
            select(PracticeSession)
            .where(PracticeSession.status == "active")
            .options(
                selectinload(PracticeSession.problem), selectinload(PracticeSession.submissions)
            )
            .order_by(PracticeSession.id.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        active = res.scalar_one_or_none()
        if not active:
            return None
        return await self._to_session_schema(active)

    async def get_session(self, session_id: int) -> PracticeSessionResponseSchema | None:
        """Fetch a specific session by its ID."""
        stmt = (
            select(PracticeSession)
            .where(PracticeSession.id == session_id)
            .options(
                selectinload(PracticeSession.problem), selectinload(PracticeSession.submissions)
            )
        )
        res = await self.session.execute(stmt)
        sess = res.scalar_one_or_none()
        if not sess:
            return None
        return await self._to_session_schema(sess)

    async def stop_session(
        self, session_id: int | None = None
    ) -> PracticeSessionResponseSchema | None:
        """Stop an active workout session manually."""
        stmt = select(PracticeSession).options(
            selectinload(PracticeSession.problem), selectinload(PracticeSession.submissions)
        )
        if session_id:
            stmt = stmt.where(PracticeSession.id == session_id)
        else:
            stmt = (
                stmt.where(PracticeSession.status == "active")
                .order_by(PracticeSession.id.desc())
                .limit(1)
            )

        res = await self.session.execute(stmt)
        active_sess = res.scalar_one_or_none()
        if not active_sess:
            return None

        now = datetime.now(UTC)
        active_sess.status = "stopped"
        active_sess.finished_at = now
        if active_sess.started_at:
            active_sess.total_duration_seconds = (
                _to_utc(now) - _to_utc(active_sess.started_at)
            ).total_seconds()

        await self.session.commit()
        await self.session.refresh(active_sess, ["problem", "submissions"])
        return await self._to_session_schema(active_sess)

    async def submit_code(
        self, req: SubmissionCreateRequest
    ) -> tuple[SubmissionResponseSchema, PracticeSessionResponseSchema | None]:
        """Submit code, judge it against test cases, and stop timer on AC."""
        # Find problem
        prob_stmt = select(Problem).where(Problem.slug == req.problem_slug)
        prob_res = await self.session.execute(prob_stmt)
        problem = prob_res.scalar_one_or_none()
        if not problem:
            raise ValueError(f"Problem '{req.problem_slug}' not found")

        # Find active session if session_id provided or inferred
        practice_session: PracticeSession | None = None
        if req.session_id:
            sess_stmt = (
                select(PracticeSession)
                .where(PracticeSession.id == req.session_id)
                .options(
                    selectinload(PracticeSession.problem), selectinload(PracticeSession.submissions)
                )
            )
            sess_res = await self.session.execute(sess_stmt)
            practice_session = sess_res.scalar_one_or_none()

        if not practice_session:
            # Check for active session containing problem
            active_stmt = (
                select(PracticeSession)
                .where(PracticeSession.status == "active")
                .options(
                    selectinload(PracticeSession.problem), selectinload(PracticeSession.submissions)
                )
                .order_by(PracticeSession.id.desc())
                .limit(1)
            )
            active_res = await self.session.execute(active_stmt)
            cand = active_res.scalar_one_or_none()
            if cand:
                p_ids = cand.problem_ids or [cand.problem_id]
                if problem.id in p_ids or cand.problem_id == problem.id:
                    practice_session = cand

        # Ensure testcases are generated from info.toml and cached in the database
        has_generated = any(
            tc.get("name", "").startswith(("random", "max_random", "gen", "small", "edge", "test"))
            for tc in (problem.sample_cases or [])
        )
        if not has_generated:
            try:
                from implegym.problems.yosupo_syncer import YosupoSyncer

                syncer = YosupoSyncer(self.session)
                synced_data = await syncer.sync_problem(problem.slug)
                if synced_data and synced_data.get("sample_cases"):
                    problem.sample_cases = synced_data["sample_cases"]
                    await self.session.commit()
            except Exception:
                pass

        # Run Judge Evaluation against full cached testcases
        run_res: JudgeRunResult = self.judge.evaluate(
            code=req.code,
            sample_cases=problem.sample_cases or [],
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

        # Update session timer and statuses if AC
        if practice_session:
            practice_session.submission_count += 1
            statuses = dict(practice_session.problem_statuses or {})
            if run_res.verdict == "AC":
                statuses[str(problem.id)] = "ac"
            practice_session.problem_statuses = statuses

            # Check if all problems in contest session are AC
            all_prob_ids = practice_session.problem_ids or [practice_session.problem_id]
            all_solved = all(statuses.get(str(pid)) == "ac" for pid in all_prob_ids)

            if all_solved and practice_session.status == "active":
                practice_session.status = "ac"
                now = datetime.now(UTC)
                practice_session.finished_at = now
                if practice_session.started_at:
                    start_utc = _to_utc(practice_session.started_at)
                    practice_session.total_duration_seconds = (now - start_utc).total_seconds()

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

    async def list_session_history(self, limit: int = 50) -> list[PracticeSessionResponseSchema]:
        """List past practice sessions for history tab."""
        stmt = (
            select(PracticeSession)
            .options(
                selectinload(PracticeSession.problem), selectinload(PracticeSession.submissions)
            )
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

        # Retrieve all problem entities in the contest session
        problem_ids = practice_session.problem_ids or [practice_session.problem_id]
        probs_stmt = select(Problem).where(Problem.id.in_(problem_ids))
        probs_res = await self.session.execute(probs_stmt)
        loaded_problems = {p.id: p for p in probs_res.scalars().all()}

        ordered_problem_schemas = [
            ProblemResponseSchema.model_validate(loaded_problems[pid])
            for pid in problem_ids
            if pid in loaded_problems
        ]
        if not ordered_problem_schemas:
            ordered_problem_schemas = [prob_schema]

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

        target_time = prob.difficulty * 5 * 60.0 if prob else 1500.0
        total_target_time = sum(p.difficulty * 5 * 60.0 for p in ordered_problem_schemas)

        statuses = practice_session.problem_statuses or {}
        solved_count = sum(1 for pid in problem_ids if statuses.get(str(pid)) == "ac")

        is_successful = None
        if practice_session.status == "ac" and practice_session.total_duration_seconds is not None:
            is_successful = practice_session.total_duration_seconds <= total_target_time

        contest_name = practice_session.name or f"Gym Contest - #{practice_session.id}"

        return PracticeSessionResponseSchema(
            id=practice_session.id,
            name=contest_name,
            problem_id=practice_session.problem_id,
            problem=prob_schema,
            problem_ids=problem_ids,
            problems=ordered_problem_schemas,
            current_problem_index=practice_session.current_problem_index or 0,
            problem_statuses=statuses,
            num_problems=len(ordered_problem_schemas),
            solved_count=solved_count,
            status=practice_session.status,
            is_manual_selection=practice_session.is_manual_selection,
            started_at=_to_utc(practice_session.started_at),
            finished_at=_to_utc(practice_session.finished_at),
            total_duration_seconds=practice_session.total_duration_seconds,
            target_time_seconds=target_time,
            total_target_time_seconds=total_target_time,
            is_successful=is_successful,
            submission_count=practice_session.submission_count,
            submissions=submissions_schema,
        )
