"""Performance benchmark tests for sampling and judging subsystems."""

import pytest
from implegym.judge.runner import OutputComparator
from implegym.models.schemas import SamplerConfigSchema
from implegym.sampler.distribution import GaussianSampler


@pytest.mark.benchmark
def test_benchmark_sampler_distribution_computation(benchmark: pytest.FixtureRequest) -> None:
    """Benchmark the probability distribution calculation over 10 discrete difficulties."""
    config = SamplerConfigSchema(mean_difficulty=5.5, standard_deviation=1.5, skewness="balanced")

    def run_computation() -> None:
        GaussianSampler.compute_difficulty_probabilities(config)

    # Simple timing test if pytest-benchmark is present or fallback
    for _ in range(1000):
        run_computation()


def test_benchmark_comparator_throughput() -> None:
    """Benchmark output comparator performance on 100k tokens."""
    actual = " ".join([str(i) for i in range(50000)]) + "\n"
    expected = " ".join([str(i) for i in range(50000)])

    assert OutputComparator.is_matching(actual, expected) is True
