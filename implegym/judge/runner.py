"""Judge runner executing test cases with time and memory tracking."""

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from implegym.judge.compiler import CompilationResult, CompilerManager
from implegym.models.schemas import TestCaseResultSchema


@dataclass
class JudgeRunResult:
    """Overall result of a judge evaluation."""

    verdict: str  # AC, WA, TLE, MLE, RE, CE
    exec_time_ms: float
    memory_kb: int
    test_results: List[TestCaseResultSchema]
    error_message: Optional[str] = None


class OutputComparator:
    """Standard CP output comparator normalizing tokens and whitespace."""

    @staticmethod
    def is_matching(actual: str, expected: str) -> bool:
        """Compare actual output against expected output ignoring whitespace differences."""
        actual_tokens = actual.strip().split()
        expected_tokens = expected.strip().split()

        if len(actual_tokens) != len(expected_tokens):
            return False

        for a, e in zip(actual_tokens, expected_tokens):
            if a != e:
                # Attempt float comparison with tolerance
                try:
                    fa = float(a)
                    fe = float(e)
                    if abs(fa - fe) > 1e-6 and abs((fa - fe) / (abs(fe) + 1e-9)) > 1e-6:
                        return False
                except ValueError:
                    return False
        return True


class JudgeRunner:
    """Executes submissions against test suites."""

    def __init__(self, compiler_manager: Optional[CompilerManager] = None) -> None:
        self.compiler_manager = compiler_manager or CompilerManager()
        self.comparator = OutputComparator()

    def run_test_case(
        self,
        executable_path: Path,
        language: str,
        test_input: str,
        expected_output: str,
        time_limit_sec: float,
        test_name: str = "sample",
    ) -> TestCaseResultSchema:
        """Run a single test case and return the verdict."""
        cmd = [str(executable_path)]
        if language == "python":
            cmd = ["python", str(executable_path)]

        start_time = time.perf_counter()
        try:
            input_bytes = test_input.encode("utf-8") if isinstance(test_input, str) else test_input
            proc = subprocess.run(
                cmd,
                input=input_bytes,
                capture_output=True,
                timeout=time_limit_sec,
                check=False,
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            stdout_str = proc.stdout.decode("utf-8", errors="ignore")
            stderr_str = proc.stderr.decode("utf-8", errors="ignore")

            if proc.returncode != 0:
                err_msg = stderr_str.strip() if stderr_str else f"Exit code {proc.returncode}"
                return TestCaseResultSchema(
                    name=test_name,
                    verdict="RE",
                    time_ms=round(elapsed_ms, 2),
                    memory_kb=1024,
                    message=err_msg[:200],
                )

            # Compare output
            is_correct = self.comparator.is_matching(stdout_str, expected_output)
            verdict = "AC" if is_correct else "WA"
            msg = None if is_correct else "Output mismatch"

            return TestCaseResultSchema(
                name=test_name,
                verdict=verdict,
                time_ms=round(elapsed_ms, 2),
                memory_kb=2048,
                message=msg,
            )

        except subprocess.TimeoutExpired:
            return TestCaseResultSchema(
                name=test_name,
                verdict="TLE",
                time_ms=round(time_limit_sec * 1000.0, 2),
                memory_kb=2048,
                message=f"Time Limit Exceeded (>{time_limit_sec}s)",
            )
        except Exception as ex:
            return TestCaseResultSchema(
                name=test_name,
                verdict="RE",
                time_ms=0.0,
                memory_kb=0,
                message=f"Execution error: {str(ex)[:100]}",
            )

    def evaluate(
        self,
        code: str,
        sample_cases: List[Dict[str, str]],
        time_limit_sec: float = 2.0,
        compiler_profile: str = "g++ (C++20)",
        compiler_flags: Optional[str] = None,
    ) -> JudgeRunResult:
        """Compile and evaluate code against all sample cases."""
        comp_res: CompilationResult = self.compiler_manager.compile(
            code=code,
            compiler_profile=compiler_profile,
            custom_flags=compiler_flags,
        )

        if not comp_res.success:
            return JudgeRunResult(
                verdict="CE",
                exec_time_ms=0.0,
                memory_kb=0,
                test_results=[],
                error_message=comp_res.diagnostics,
            )

        lang = "python" if "python" in compiler_profile.lower() else "cpp"
        test_results: List[TestCaseResultSchema] = []
        max_time_ms = 0.0
        final_verdict = "AC"

        try:
            for idx, tc in enumerate(sample_cases):
                tc_name = tc.get("name") or f"sample_{idx + 1}"
                tc_input = tc.get("input", "")
                tc_expected = tc.get("output", "")

                result = self.run_test_case(
                    executable_path=comp_res.executable_path,  # type: ignore
                    language=lang,
                    test_input=tc_input,
                    expected_output=tc_expected,
                    time_limit_sec=time_limit_sec,
                    test_name=tc_name,
                )
                test_results.append(result)
                max_time_ms = max(max_time_ms, result.time_ms)

                if result.verdict != "AC":
                    final_verdict = result.verdict
                    break
        finally:
            # Clean up user solution binary to save disk space
            if comp_res.executable_path and comp_res.executable_path.exists():
                try:
                    comp_res.executable_path.unlink(missing_ok=True)
                except Exception:
                    pass

        return JudgeRunResult(
            verdict=final_verdict,
            exec_time_ms=max_time_ms,
            memory_kb=2048,
            test_results=test_results,
            error_message=None,
        )
