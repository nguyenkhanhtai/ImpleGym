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

        # Batch-fetch solve statistics for all problems on the page
        enriched: List[ProblemResponseSchema] = []
        if problems:
            prob_ids = [p.id for p in problems]

            # 1. Best AC duration per problem
            sess_stmt = (
                select(
                    PracticeSession.problem_id,
                    func.min(PracticeSession.total_duration_seconds).label("best_duration"),
                )
                .where(
                    PracticeSession.problem_id.in_(prob_ids),
                    PracticeSession.status == "ac",
                    PracticeSession.total_duration_seconds.isnot(None),
                )
                .group_by(PracticeSession.problem_id)
            )
            sess_res = await self.session.execute(sess_stmt)
            best_session_map = {row.problem_id: row.best_duration for row in sess_res.all()}

            # 2. Standalone AC submission count per problem
            sub_stmt = (
                select(
                    Submission.problem_id,
                    func.count(Submission.id).label("ac_count"),
                )
                .where(
                    Submission.problem_id.in_(prob_ids),
                    Submission.verdict == "AC",
                )
                .group_by(Submission.problem_id)
            )
            sub_res = await self.session.execute(sub_stmt)
            ac_count_map = {row.problem_id: row.ac_count for row in sub_res.all()}

            for prob in problems:
                best_time = best_session_map.get(prob.id)
                target_seconds = prob.difficulty * 5 * 60.0

                if best_time is not None:
                    solved = True
                    successful = best_time <= target_seconds
                else:
                    ac_count = ac_count_map.get(prob.id, 0)
                    solved = ac_count > 0
                    successful = False

                if params.solved_status == "successful" and not successful:
                    continue
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
                    is_difficulty_customized=getattr(prob, "is_difficulty_customized", False),
                    created_at=prob.created_at,
                    is_solved=solved,
                    is_successful=successful,
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

        solved, successful, best_time = await self._get_solve_stats(prob.id, prob.difficulty)
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
            is_difficulty_customized=getattr(prob, "is_difficulty_customized", False),
            created_at=prob.created_at,
            is_solved=solved,
            is_successful=successful,
            best_time_seconds=best_time,
        )

    async def update_problem(
        self, slug: str, update_data: Dict[str, Any]
    ) -> Optional[ProblemResponseSchema]:
        """Update problem properties (difficulty, title, category, tags)."""
        stmt = select(Problem).where(Problem.slug == slug)
        res = await self.session.execute(stmt)
        prob = res.scalar_one_or_none()
        if not prob:
            return None

        if "difficulty" in update_data and update_data["difficulty"] is not None:
            prob.difficulty = int(update_data["difficulty"])
            prob.is_difficulty_customized = True
        if "title" in update_data and update_data["title"] is not None:
            prob.title = update_data["title"]
        if "category" in update_data and update_data["category"] is not None:
            prob.category = update_data["category"]
        if "tags" in update_data and update_data["tags"] is not None:
            prob.tags = update_data["tags"]

        await self.session.commit()
        await self.session.refresh(prob)
        return await self.get_by_slug(slug)

    async def get_all_categories(self) -> List[str]:
        """Get unique categories."""
        stmt = select(Problem.category).distinct().order_by(Problem.category.asc())
        res = await self.session.execute(stmt)
        return [row[0] for row in res.all()]

    async def _get_solve_stats(
        self, problem_id: int, difficulty: int
    ) -> Tuple[bool, bool, Optional[float]]:
        """Determine if problem has been ACed, whether it met target time (diff * 5 min), and best solve duration."""
        target_seconds = difficulty * 5 * 60.0
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
            is_successful = best_duration <= target_seconds
            return True, is_successful, best_duration

        # Also check standalone AC submissions
        sub_stmt = (
            select(func.count())
            .select_from(Submission)
            .where(Submission.problem_id == problem_id, Submission.verdict == "AC")
        )
        sub_res = await self.session.execute(sub_stmt)
        ac_count = sub_res.scalar_one()
        return (ac_count > 0), False, None
