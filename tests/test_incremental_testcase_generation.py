"""Tests verifying incremental testcase generation and disk persistence."""

from pathlib import Path
from unittest.mock import MagicMock

from implegym.problems.yosupo_syncer import YosupoSyncer


def test_incremental_testcase_generation_lifecycle(tmp_path: Path) -> None:
    """Verify testcases are generated onto disk and skipped when already present."""
    # 1. Setup mock Yosupo problem directory
    prob_dir = tmp_path / "mock_problem"
    gen_dir = prob_dir / "gen"
    sol_dir = prob_dir / "sol"
    gen_dir.mkdir(parents=True)
    sol_dir.mkdir(parents=True)

    # info.toml
    info_toml = prob_dir / "info.toml"
    info_toml.write_text(
        """
title = "Mock Increment Problem"
timelimit = 2.0

[[tests]]
    name = "random.cpp"
    number = 2

[params]
    N_MAX = 100
""",
        encoding="utf-8",
    )

    # task.md
    task_md = prob_dir / "task.md"
    task_md.write_text("# Mock Task\nProblem statement here.", encoding="utf-8")

    # gen/random.cpp
    gen_cpp = gen_dir / "random.cpp"
    gen_cpp.write_text(
        r"""
#include <iostream>
int main(int argc, char* argv[]) {
    int seed = (argc > 1) ? std::atoi(argv[1]) : 1;
    std::cout << seed << " " << (seed * 2) << "\n";
    return 0;
}
""",
        encoding="utf-8",
    )

    # sol/correct.cpp
    sol_cpp = sol_dir / "correct.cpp"
    sol_cpp.write_text(
        r"""
#include <iostream>
int main() {
    long long a, b;
    if (std::cin >> a >> b) {
        std::cout << (a + b) << "\n";
    }
    return 0;
}
""",
        encoding="utf-8",
    )

    target_disk_dir = tmp_path / "testcases" / "mock_problem"

    syncer = YosupoSyncer(MagicMock())

    # First run: generates test files onto disk
    tests_1 = syncer._generate_testcases_from_info_toml(
        problem_dir=prob_dir,
        params={"N_MAX": 100},
        max_tests=2,
        target_dir=target_disk_dir,
        force=False,
    )

    assert len(tests_1) == 2
    in_files = sorted(target_disk_dir.glob("*.in"))
    out_files = sorted(target_disk_dir.glob("*.out"))
    assert len(in_files) == 2
    assert len(out_files) == 2

    # Check contents of generated files
    assert in_files[0].name == "random_01.in"
    assert (target_disk_dir / "random_01.in").read_text(encoding="utf-8").strip() == "1 2"
    assert (target_disk_dir / "random_01.out").read_text(encoding="utf-8").strip() == "3"

    # Record modification times
    mtime_1 = in_files[0].stat().st_mtime

    # Second run without force: should skip compilation & generation and reuse disk files
    tests_2 = syncer._generate_testcases_from_info_toml(
        problem_dir=prob_dir,
        params={"N_MAX": 100},
        max_tests=2,
        target_dir=target_disk_dir,
        force=False,
    )

    assert len(tests_2) == 2
    mtime_2 = in_files[0].stat().st_mtime
    assert mtime_1 == mtime_2  # File was untouched

    # Third run with force: regenerates files
    tests_3 = syncer._generate_testcases_from_info_toml(
        problem_dir=prob_dir,
        params={"N_MAX": 100},
        max_tests=2,
        target_dir=target_disk_dir,
        force=True,
    )
    assert len(tests_3) == 2


def test_extraneous_file_purge_in_testcases_dir(tmp_path: Path) -> None:
    """Verify that any rogue or unlisted files in testcases directory are automatically deleted."""
    prob_dir = tmp_path / "mock_problem2"
    gen_dir = prob_dir / "gen"
    sol_dir = prob_dir / "sol"
    gen_dir.mkdir(parents=True)
    sol_dir.mkdir(parents=True)

    info_toml = prob_dir / "info.toml"
    info_toml.write_text(
        """
title = "Mock Purge Problem"
timelimit = 2.0

[[tests]]
    name = "small.cpp"
    number = 2
""",
        encoding="utf-8",
    )

    gen_cpp = gen_dir / "small.cpp"
    gen_cpp.write_text(
        r"""
#include <iostream>
int main() {
    std::cout << "42\n";
    return 0;
}
""",
        encoding="utf-8",
    )

    sol_cpp = sol_dir / "correct.cpp"
    sol_cpp.write_text(
        r"""
#include <iostream>
int main() {
    int x;
    if (std::cin >> x) std::cout << x << "\n";
    return 0;
}
""",
        encoding="utf-8",
    )

    target_disk_dir = tmp_path / "testcases" / "mock_problem2"
    target_disk_dir.mkdir(parents=True)

    # Place extraneous rogue files in target directory
    rogue_1 = target_disk_dir / "old_random_99.in"
    rogue_2 = target_disk_dir / "corrupted_temp.out"
    sample_f = target_disk_dir / "00_sample_00.in"
    rogue_1.write_text("rogue data", encoding="utf-8")
    rogue_2.write_text("rogue data", encoding="utf-8")
    sample_f.write_text("sample data", encoding="utf-8")

    syncer = YosupoSyncer(MagicMock())
    syncer._generate_testcases_from_info_toml(
        problem_dir=prob_dir,
        params={},
        target_dir=target_disk_dir,
        force=False,
    )

    # Rogue files must be wiped out
    assert not rogue_1.exists()
    assert not rogue_2.exists()

    # Official sample and valid generated test files must be present
    assert sample_f.exists()
    assert (target_disk_dir / "small_01.in").exists()
    assert (target_disk_dir / "small_01.out").exists()
    assert (target_disk_dir / "small_02.in").exists()
    assert (target_disk_dir / "small_02.out").exists()
