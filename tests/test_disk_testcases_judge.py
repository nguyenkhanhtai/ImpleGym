"""Comprehensive tests verifying on-disk testcase file streaming and judge evaluation lifecycle."""

from pathlib import Path

from implegym.judge.runner import JudgeRunner, OutputComparator


def test_output_comparator_edge_cases() -> None:
    """Verify OutputComparator handles whitespace, newlines, and float tolerances."""
    comp = OutputComparator()
    # 1. Exact match with whitespace differences
    assert comp.is_matching("1 2 3\n", "1\n2\n3\n\n")
    assert comp.is_matching("  15 \n", "15")

    # 2. Float tolerances
    assert comp.is_matching("3.14159265", "3.14159266")
    assert not comp.is_matching("3.14", "3.15")

    # 3. Token count mismatch
    assert not comp.is_matching("1 2 3", "1 2")
    assert not comp.is_matching("", "1")


def test_judge_runner_file_streaming_ac(tmp_path: Path) -> None:
    """Verify run_test_file streams stdin directly from disk and verifies output."""
    runner = JudgeRunner()

    # Create dummy test input and output files on disk
    in_file = tmp_path / "01_test.in"
    out_file = tmp_path / "01_test.out"
    in_file.write_text("10 20\n", encoding="utf-8")
    out_file.write_text("30\n", encoding="utf-8")

    # Compile simple C++ addition solution
    cpp_code = r"""
#include <iostream>
using namespace std;
int main() {
    long long a, b;
    if (cin >> a >> b) {
        cout << (a + b) << "\n";
    }
    return 0;
}
"""
    comp_res = runner.compiler_manager.compile(cpp_code, "g++ (C++20)")
    assert comp_res.success
    assert comp_res.executable_path is not None

    try:
        res = runner.run_test_file(
            executable_path=comp_res.executable_path,
            language="cpp",
            in_file_path=in_file,
            out_file_path=out_file,
            time_limit_sec=2.0,
            test_name="01_test",
        )
        assert res.verdict == "AC"
        assert res.name == "01_test"
        assert res.time_ms >= 0.0
    finally:
        comp_res.executable_path.unlink(missing_ok=True)


def test_judge_runner_file_streaming_wa_and_re(tmp_path: Path) -> None:
    """Verify run_test_file detects Wrong Answer and Runtime Error from disk files."""
    runner = JudgeRunner()

    in_file = tmp_path / "01_test.in"
    out_file = tmp_path / "01_test.out"
    in_file.write_text("5 5\n", encoding="utf-8")
    out_file.write_text("100\n", encoding="utf-8")  # Expected 100 but code will output 10

    # 1. Test WA (Wrong Answer)
    cpp_wa = r"""
#include <iostream>
using namespace std;
int main() {
    long long a, b;
    cin >> a >> b;
    cout << (a + b) << "\n";
    return 0;
}
"""
    comp_wa = runner.compiler_manager.compile(cpp_wa, "g++ (C++20)")
    assert comp_wa.success
    try:
        res_wa = runner.run_test_file(
            executable_path=comp_wa.executable_path,  # type: ignore
            language="cpp",
            in_file_path=in_file,
            out_file_path=out_file,
            time_limit_sec=2.0,
            test_name="wa_test",
        )
        assert res_wa.verdict == "WA"
        assert res_wa.message == "Output mismatch"
    finally:
        comp_wa.executable_path.unlink(missing_ok=True)  # type: ignore

    # 2. Test RE (Runtime Error / Crash)
    cpp_re = r"""
#include <iostream>
using namespace std;
int main() {
    int* p = nullptr;
    *p = 42; // Segfault
    return 0;
}
"""
    comp_re = runner.compiler_manager.compile(cpp_re, "g++ (C++20)")
    assert comp_re.success
    try:
        res_re = runner.run_test_file(
            executable_path=comp_re.executable_path,  # type: ignore
            language="cpp",
            in_file_path=in_file,
            out_file_path=out_file,
            time_limit_sec=2.0,
            test_name="re_test",
        )
        assert res_re.verdict == "RE"
    finally:
        comp_re.executable_path.unlink(missing_ok=True)  # type: ignore


def test_judge_runner_evaluate_directory(tmp_path: Path) -> None:
    """Verify evaluate() runs all testcase files in a directory in sorted order."""
    runner = JudgeRunner()
    tc_dir = tmp_path / "testcases" / "sum_problem"
    tc_dir.mkdir(parents=True)

    # Create 3 test files
    for i in range(1, 4):
        (tc_dir / f"test_{i:02d}.in").write_text(f"{i} {i * 10}\n", encoding="utf-8")
        (tc_dir / f"test_{i:02d}.out").write_text(f"{i + i * 10}\n", encoding="utf-8")

    cpp_sol = r"""
#include <iostream>
using namespace std;
int main() {
    long long a, b;
    while (cin >> a >> b) {
        cout << (a + b) << "\n";
    }
    return 0;
}
"""
    run_res = runner.evaluate(
        code=cpp_sol,
        testcases_dir=tc_dir,
        time_limit_sec=2.0,
        compiler_profile="g++ (C++20)",
    )

    assert run_res.verdict == "AC"
    assert len(run_res.test_results) == 3
    assert [t.name for t in run_res.test_results] == ["test_01", "test_02", "test_03"]


def test_judge_runner_python_file_streaming(tmp_path: Path) -> None:
    """Verify Python submissions execute and stream test files correctly."""
    runner = JudgeRunner()
    tc_dir = tmp_path / "py_tests"
    tc_dir.mkdir(parents=True)

    (tc_dir / "01.in").write_text("hello world\n", encoding="utf-8")
    (tc_dir / "01.out").write_text("HELLO WORLD\n", encoding="utf-8")

    py_code = """
import sys
text = sys.stdin.read().strip()
print(text.upper())
"""
    run_res = runner.evaluate(
        code=py_code,
        testcases_dir=tc_dir,
        time_limit_sec=2.0,
        compiler_profile="python3",
    )

    assert run_res.verdict == "AC"
    assert len(run_res.test_results) == 1
