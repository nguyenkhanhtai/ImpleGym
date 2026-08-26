"""Backward compatibility shim for YosupoSyncer -> ProblemSyncer."""

from implegym.problems.syncer import (
    CATEGORY_DIFFICULTY_BASELINE,
    KNOWN_PROBLEM_DIFFICULTIES,
    ProblemSyncer,
    YosupoSyncer,
)

__all__ = [
    "ProblemSyncer",
    "YosupoSyncer",
    "CATEGORY_DIFFICULTY_BASELINE",
    "KNOWN_PROBLEM_DIFFICULTIES",
]
