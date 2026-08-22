"""Judge runner and differential test execution tests."""

from implegym.judge.runner import JudgeRunner, OutputComparator


class TestJudgeRunner:
    """Test suite for judge evaluation, verdicts, and comparator."""

    def setup_method(self) -> None:
        self.judge = JudgeRunner()

    def test_output_comparator_normalization(self) -> None:
        """Test whitespace-normalized output comparison."""
        assert OutputComparator.is_matching("1 2 3\n", "1 2 3") is True
        assert OutputComparator.is_matching("  10.0000001 \n", "10.0000002") is True
        assert OutputComparator.is_matching("3\n", "4\n") is False
        assert OutputComparator.is_matching("1 2", "1 2 3") is False

    def test_judge_accepted_verdict(self) -> None:
        """Test accepted solution."""
        code = """
        #include <iostream>
        using namespace std;
        int main() {
            long long a, b;
            if (cin >> a >> b) {
                cout << (a + b) << "\\n";
            }
            return 0;
        }
        """
        samples = [
            {"input": "1 2\n", "output": "3\n"},
            {"input": "100 200\n", "output": "300\n"},
        ]
        res = self.judge.evaluate(code, sample_cases=samples, time_limit_sec=2.0)
        assert res.verdict == "AC"
        assert len(res.test_results) == 2
        assert all(tc.verdict == "AC" for tc in res.test_results)

    def test_judge_wrong_answer_verdict(self) -> None:
        """Test wrong answer solution."""
        code = """
        #include <iostream>
        using namespace std;
        int main() {
            long long a, b;
            cin >> a >> b;
            cout << (a * b) << "\\n"; // Multiply instead of add
            return 0;
        }
        """
        samples = [{"input": "2 3\n", "output": "5\n"}]
        res = self.judge.evaluate(code, sample_cases=samples, time_limit_sec=2.0)
        assert res.verdict == "WA"
        assert res.test_results[0].verdict == "WA"

    def test_judge_time_limit_exceeded(self) -> None:
        """Test TLE detection on infinite loop."""
        code = """
        #include <iostream>
        int main() {
            while (true) {}
            return 0;
        }
        """
        samples = [{"input": "1 2\n", "output": "3\n"}]
        res = self.judge.evaluate(code, sample_cases=samples, time_limit_sec=0.5)
        assert res.verdict == "TLE"
        assert res.test_results[0].verdict == "TLE"

    def test_judge_runtime_error(self) -> None:
        """Test RE detection on non-zero exit code / error."""
        code = """
        #include <iostream>
        int main() {
            return 1; // Exit with runtime failure code
        }
        """
        samples = [{"input": "1\n", "output": "1\n"}]
        res = self.judge.evaluate(code, sample_cases=samples, time_limit_sec=2.0)
        assert res.verdict == "RE"
        assert res.test_results[0].verdict == "RE"
