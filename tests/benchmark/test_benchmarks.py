"""Performance benchmark tests for sampling and judging subsystems."""

from typing import Any
from implegym.judge.runner import OutputComparator
from implegym.models.schemas import SamplerConfigSchema
from implegym.sampler.distribution import GaussianSampler


def test_benchmark_sampler_distribution_computation(benchmark: Any) -> None:
    """Benchmark the probability distribution calculation over 10 discrete difficulties."""
    config = SamplerConfigSchema(mean_difficulty=5.5, standard_deviation=1.5, skewness="balanced")
    
    # Properly invoke the benchmark fixture
    result = benchmark(GaussianSampler.compute_difficulty_probabilities, config)
    assert len(result) == 10
    assert 1 in result


def test_benchmark_comparator_throughput(benchmark: Any) -> None:
    """Benchmark output comparator performance on 50k tokens."""
    actual = " ".join([str(i) for i in range(50000)]) + "\n"
    expected = " ".join([str(i) for i in range(50000)])

    result = benchmark(OutputComparator.is_matching, actual, expected)
    assert result is True
