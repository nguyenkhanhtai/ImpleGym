"""Gaussian and Skew-Normal difficulty sampling engine."""

import random

import numpy as np
from scipy import stats
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from implegym.db.models import PracticeSession, Problem
from implegym.models.schemas import ProblemResponseSchema, SamplerConfigSchema


class GaussianSampler:
    """Mathematical difficulty sampler supporting Normal and Skew-Normal distributions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def compute_difficulty_probabilities(config: SamplerConfigSchema) -> dict[int, float]:
        """Calculate discrete probability distribution over difficulties 1 to 10."""
        mean = config.mean_difficulty
        std = max(0.1, config.standard_deviation)
        skew = config.skewness.lower()

        # Skew parameter alpha for Azzalini's skew normal
        alpha = 0.0
        if skew == "left":
            alpha = -4.0  # Left-skewed, heavy lower tail
            mean = max(2.5, mean - 1.5)
        elif skew == "right":
            alpha = 4.0  # Right-skewed, heavy upper tail
            mean = min(8.5, mean + 1.5)

        difficulties = np.arange(1, 11)
        # Compute PDF at discrete integer points
        pdf_values = stats.skewnorm.pdf(difficulties, a=alpha, loc=mean, scale=std)

        # Normalize to sum to 1.0
        total_mass = np.sum(pdf_values)
        if total_mass <= 1e-12:
            # Fallback uniform if degenerated
            return dict.fromkeys(range(1, 11), 0.1)

        probs = pdf_values / total_mass
        return {int(d): float(p) for d, p in zip(difficulties, probs, strict=False)}

    async def sample_problem(self, config: SamplerConfigSchema) -> ProblemResponseSchema | None:
        """Sample a single problem from database according to configured probability distribution."""
        probs = await self.sample_problems(config, count=1)
        return probs[0] if probs else None

    async def sample_problems(
        self, config: SamplerConfigSchema, count: int | None = None
    ) -> list[ProblemResponseSchema]:
        """Sample N problems (1 <= N <= 14) from database according to configured probability distribution."""
        target_count = max(1, min(14, count if count is not None else config.num_problems))
        probs_map = self.compute_difficulty_probabilities(config)

        # Retrieve all candidate problems with filters (excluding test category)
        query = select(Problem).where(func.lower(Problem.category) != "test")
        if config.category:
            query = query.where(func.lower(Problem.category) == config.category.strip().lower())

        res = await self.session.execute(query)
        candidates = list(res.scalars().all())

        if config.tag:
            tag_clean = config.tag.strip().lower()
            candidates = [
                p
                for p in candidates
                if any(str(t).strip().lower() == tag_clean for t in (p.tags or []))
            ]

        if not candidates:
            return []

        # Filter out solved problems if requested
        if config.exclude_solved:
            solved_stmt = select(PracticeSession.problem_id).where(PracticeSession.status == "ac")
            solved_res = await self.session.execute(solved_stmt)
            solved_ids = set(solved_res.scalars().all())
            candidates = [p for p in candidates if p.id not in solved_ids]

        if not candidates:
            return []
        from collections import defaultdict

        chosen_problems: list[Problem] = []
        available_candidates = list(candidates)

        for _ in range(target_count):
            if not available_candidates:
                break

            # Recalculate diff buckets for remaining available candidates
            curr_diff_buckets: dict[int, list[Problem]] = defaultdict(list)
            for p in available_candidates:
                curr_diff_buckets[p.difficulty].append(p)

            sampled_difficulties = list(probs_map.keys())
            sampled_weights = [
                probs_map[d] if len(curr_diff_buckets[d]) > 0 else 0.0 for d in sampled_difficulties
            ]

            if sum(sampled_weights) <= 1e-12:
                chosen = random.choice(available_candidates)
            else:
                chosen_diff = random.choices(sampled_difficulties, weights=sampled_weights, k=1)[0]
                chosen = random.choice(curr_diff_buckets[chosen_diff])

            chosen_problems.append(chosen)
            available_candidates.remove(chosen)

        return [ProblemResponseSchema.model_validate(p) for p in chosen_problems]
