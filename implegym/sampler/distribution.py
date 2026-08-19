"""Gaussian and Skew-Normal difficulty sampling engine."""

import math
import random
from typing import Dict, List, Optional
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
    def compute_difficulty_probabilities(config: SamplerConfigSchema) -> Dict[int, float]:
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
            return {d: 0.1 for d in range(1, 11)}

        probs = pdf_values / total_mass
        return {int(d): float(p) for d, p in zip(difficulties, probs)}

    async def sample_problem(self, config: SamplerConfigSchema) -> Optional[ProblemResponseSchema]:
        """Sample a problem from database according to configured probability distribution."""
        probs_map = self.compute_difficulty_probabilities(config)

        # Retrieve all candidate problems with filters
        query = select(Problem)
        if config.category:
            query = query.where(func.lower(Problem.category) == config.category.strip().lower())
        if config.tag:
            query = query.where(Problem.tags.contains([config.tag.strip()]))

        res = await self.session.execute(query)
        candidates = list(res.scalars().all())

        if not candidates:
            return None

        # Filter out solved problems if requested
        if config.exclude_solved:
            solved_stmt = select(PracticeSession.problem_id).where(PracticeSession.status == "ac")
            solved_res = await self.session.execute(solved_stmt)
            solved_ids = set(solved_res.scalars().all())
            candidates = [p for p in candidates if p.id not in solved_ids]

        if not candidates:
            return None

        # Group candidates by difficulty
        diff_buckets: Dict[int, List[Problem]] = {d: [] for d in range(1, 11)}
        for p in candidates:
            diff_buckets[p.difficulty].append(p)

        # Calculate effective bucket weights
        sampled_difficulties = list(probs_map.keys())
        sampled_weights = [
            probs_map[d] if len(diff_buckets[d]) > 0 else 0.0 for d in sampled_difficulties
        ]

        if sum(sampled_weights) <= 1e-12:
            # Uniform random choice if weights all zero
            chosen_prob = random.choice(candidates)
        else:
            # Weighted random choice of difficulty bucket
            chosen_diff = random.choices(sampled_difficulties, weights=sampled_weights, k=1)[0]
            chosen_prob = random.choice(diff_buckets[chosen_diff])

        return ProblemResponseSchema.model_validate(chosen_prob)
