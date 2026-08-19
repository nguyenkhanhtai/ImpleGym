"""Property-based testing for Gaussian and Skew-Normal sampling engine using Hypothesis."""

import math
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from implegym.models.schemas import SamplerConfigSchema
from implegym.sampler.distribution import GaussianSampler


class TestSamplerProperties:
    """Mathematical invariants test suite for difficulty sampling."""

    @given(
        mean=st.floats(min_value=1.0, max_value=10.0),
        std=st.floats(min_value=0.1, max_value=5.0),
        skewness=st.sampled_from(["balanced", "left", "right"]),
    )
    @settings(max_examples=100)
    def test_discrete_probability_distribution_invariants(
        self, mean: float, std: float, skewness: str
    ) -> None:
        """Property: Discrete probabilities must always sum to 1.0 and cover difficulties 1..10."""
        config = SamplerConfigSchema(
            mean_difficulty=mean,
            standard_deviation=std,
            skewness=skewness,
        )
        probs = GaussianSampler.compute_difficulty_probabilities(config)

        assert len(probs) == 10
        assert set(probs.keys()) == set(range(1, 11))

        # Check all probabilities non-negative
        for d, p in probs.items():
            assert p >= 0.0, f"Probability for difficulty {d} must be non-negative"

        # Check sum equals 1.0 (with float tolerance)
        total_prob = sum(probs.values())
        assert math.isclose(total_prob, 1.0, rel_tol=1e-5, abs_tol=1e-5)

    def test_skewness_direction_shift(self) -> None:
        """Property: Left-skewed distribution must allocate significantly more mass to lower difficulties."""
        left_config = SamplerConfigSchema(mean_difficulty=5.5, standard_deviation=1.5, skewness="left")
        right_config = SamplerConfigSchema(mean_difficulty=5.5, standard_deviation=1.5, skewness="right")

        left_probs = GaussianSampler.compute_difficulty_probabilities(left_config)
        right_probs = GaussianSampler.compute_difficulty_probabilities(right_config)

        # Sum probabilities for easy problems (1 to 4)
        left_easy_mass = sum(left_probs[d] for d in range(1, 5))
        right_easy_mass = sum(right_probs[d] for d in range(1, 5))

        # Left skew must have substantially more easy mass than right skew
        assert left_easy_mass > right_easy_mass

        # Sum probabilities for hard problems (7 to 10)
        left_hard_mass = sum(left_probs[d] for d in range(7, 11))
        right_hard_mass = sum(right_probs[d] for d in range(7, 11))

        assert right_hard_mass > left_hard_mass
