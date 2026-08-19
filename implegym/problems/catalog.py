"""Problem catalog service for search, filtering, and queries."""

from typing import List, Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from implegym.db.models import PracticeSession, Problem, Submission
from implegym.models.schemas import ProblemFilterParams, ProblemResponseSchema


class ProblemCatalogService:
    """Service handling problem searches, filtering, and detail extraction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_problems(
        self, params: ProblemFilterParams
    ) -> Tuple[List[ProblemResponseSchema], int]:
        """Query problems matching filter criteria with pagination."""
        query = select(Problem)

        if params.search:
            pattern = f"%{params.search.strip().lower()}%"
            query = query.where(
                func.lower(Problem.title).like(pattern)
                | func.lower(Problem.slug).like(pattern)
                | func.lower(Problem.statement).like(pattern)
            )

        if params.category:
            query = query.where(func.lower(Problem.category) == params.category.strip().lower())

        if params.min_difficulty:
            query = query.where(Problem.difficulty >= params.min_difficulty)

        if params.max_difficulty:
            query = query.where(Problem.difficulty <= params.max_difficulty)

        # Count total matches
        count_stmt = select(func.count()).select_from(query.subquery())
        total_count_res = await self.session.execute(count_stmt)
        total_count = total_count_res.scalar_one()

        # Apply ordering and pagination
        query = query.order_by(Problem.difficulty.asc(), Problem.id.asc())
        offset = (params.page - 1) * params.page_size
        query = query.offset(offset).limit(params.page_size)

        result = await self.session.execute(query)
        problems = result.scalars().all()

        # Enrich with solved status and best time
        enriched: List[ProblemResponseSchema] = []
        for prob in problems:
            solved, best_time = await self._get_solve_stats(prob.id)
            if params.solved_status == "solved" and not solved:
                continue
            if params.solved_status == "unsolved" and solved:
                continue

            schema = ProblemResponseSchema(
                id=prob.id,
                slug=prob.slug,
                title=prob.title,
                category=prob.category,
                difficulty=prob.difficulty,
                statement=prob.statement,
                input_format=prob.input_format,
                output_format=prob.output_format,
                constraints=prob.constraints,
                sample_cases=prob.sample_cases,
                time_limit=prob.time_limit,
                memory_limit_mb=prob.memory_limit_mb,
                tags=prob.tags,
                source=prob.source,
                created_at=prob.created_at,
                is_solved=solved,
                best_time_seconds=best_time,
            )
            enriched.append(schema)

        return enriched, total_count

    async def get_by_slug(self, slug: str) -> Optional[ProblemResponseSchema]:
        """Fetch problem by slug."""
        stmt = select(Problem).where(Problem.slug == slug)
        res = await self.session.execute(stmt)
        prob = res.scalar_one_or_none()
        if not prob:
            return None

        solved, best_time = await self._get_solve_stats(prob.id)
        return ProblemResponseSchema(
            id=prob.id,
            slug=prob.slug,
            title=prob.title,
            category=prob.category,
            difficulty=prob.difficulty,
            statement=prob.statement,
            input_format=prob.input_format,
            output_format=prob.output_format,
            constraints=prob.constraints,
            sample_cases=prob.sample_cases,
            time_limit=prob.time_limit,
            memory_limit_mb=prob.memory_limit_mb,
            tags=prob.tags,
            source=prob.source,
            created_at=prob.created_at,
            is_solved=solved,
            best_time_seconds=best_time,
        )

    async def get_all_categories(self) -> List[str]:
        """Get unique categories."""
        stmt = select(Problem.category).distinct().order_by(Problem.category.asc())
        res = await self.session.execute(stmt)
        return [row[0] for row in res.all()]

    async def _get_solve_stats(self, problem_id: int) -> Tuple[bool, Optional[float]]:
        """Determine if problem has been ACed and find best solve duration."""
        stmt = (
            select(PracticeSession.total_duration_seconds)
            .where(
                PracticeSession.problem_id == problem_id,
                PracticeSession.status == "ac",
                PracticeSession.total_duration_seconds.isnot(None),
            )
            .order_by(PracticeSession.total_duration_seconds.asc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        best_duration = res.scalar_one_or_none()

        if best_duration is not None:
            return True, best_duration

        # Also check standalone AC submissions
        sub_stmt = (
            select(func.count())
            .select_from(Submission)
            .where(Submission.problem_id == problem_id, Submission.verdict == "AC")
        )
        sub_res = await self.session.execute(sub_stmt)
        ac_count = sub_res.scalar_one()
        return (ac_count > 0), None
