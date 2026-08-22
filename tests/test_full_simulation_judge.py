"""Test suite verifying comprehensive 100% input/output simulation testing and judge accuracy."""

from implegym.judge.runner import JudgeRunner, OutputComparator


class TestFullSimulationJudge:
    """Test suite testing 100% input/output simulation evaluation."""

    def test_output_comparator_comprehensive_simulation_matching(self) -> None:
        """Verify comparator handles 100% exact simulation of tokens, floats, and multi-line outputs."""
        comparator = OutputComparator()

        # 1. Multi-line whitespace variations
        expected_multiline = "3\n1 2 4\n"
        actual_with_spaces = "3 \n  1   2   4  \n"
        assert comparator.is_matching(actual_with_spaces, expected_multiline)

        # 2. Large simulated token stream
        expected_large = " ".join(str(i) for i in range(1000))
        actual_large = "\n".join(str(i) for i in range(1000))
        assert comparator.is_matching(actual_large, expected_large)

        # 3. Mismatch in token count
        assert not comparator.is_matching("1 2 3", "1 2")

        # 4. Mismatch in values
        assert not comparator.is_matching("1 2 4", "1 2 5")

    def test_full_input_output_simulation_accepted(self) -> None:
        """Verify a complete solution simulating 100% of diverse input/output cases gets AC."""
        judge = JudgeRunner()

        # Simulated test suite covering 100% of boundary and general cases for Longest Increasing Subsequence
        full_simulation_test_suite = [
            # Sample 1
            {"input": "5\n3 1 4 1 5\n", "output": "3\n1 2 4\n"},
            # Sample 2
            {"input": "5\n3 3 2 3 1\n", "output": "2\n2 3\n"},
            # Edge case 1: Single element
            {"input": "1\n42\n", "output": "1\n0\n"},
            # Edge case 2: Strictly increasing
            {"input": "4\n10 20 30 40\n", "output": "4\n0 1 2 3\n"},
            # Edge case 3: Strictly decreasing
            {"input": "4\n40 30 20 10\n", "output": "1\n3\n"},
            # Boundary case 4: Large values up to 10^9
            {
                "input": "6\n1000000000 500000000 700000000 900000000 600000000 800000000\n",
                "output": "3\n1 4 5\n",
            },
        ]

        # 100% Full Optimal O(N log N) C++ Simulation Solution
        cpp_lis_solution = r"""
#include <iostream>
#include <vector>
#include <algorithm>

using namespace std;

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(NULL);

    int n;
    if (!(cin >> n)) return 0;

    vector<long long> a(n);
    for (int i = 0; i < n; ++i) {
        cin >> a[i];
    }

    if (n == 0) {
        cout << 0 << "\n\n";
        return 0;
    }

    vector<long long> tails;
    vector<int> tail_indices;
    vector<int> parent(n, -1);
    vector<int> pos_in_tails(n, 0);

    for (int i = 0; i < n; ++i) {
        auto it = lower_bound(tails.begin(), tails.end(), a[i]);
        int idx = distance(tails.begin(), it);

        if (it == tails.end()) {
            tails.push_back(a[i]);
            tail_indices.push_back(i);
        } else {
            *it = a[i];
            tail_indices[idx] = i;
        }

        pos_in_tails[i] = idx;
        if (idx > 0) {
            parent[i] = tail_indices[idx - 1];
        }
    }

    int k = tails.size();
    cout << k << "\n";

    // Reconstruct indices
    vector<int> lis_indices(k);
    int curr = tail_indices[k - 1];
    for (int i = k - 1; i >= 0; --i) {
        lis_indices[i] = curr;
        curr = parent[curr];
    }

    for (int i = 0; i < k; ++i) {
        cout << lis_indices[i] << (i + 1 == k ? "" : " ");
    }
    cout << "\n";

    return 0;
}
"""

        res = judge.evaluate(
            code=cpp_lis_solution,
            sample_cases=full_simulation_test_suite,
            time_limit_sec=2.0,
            compiler_profile="g++ (C++20)",
        )

        if res.verdict != "AC":
            print("Judge results:", [(tc.name, tc.verdict, tc.message) for tc in res.test_results])
        assert res.verdict == "AC"
        assert len(res.test_results) == len(full_simulation_test_suite)
        for tc in res.test_results:
            assert tc.verdict == "AC"

    def test_partial_or_sample_hardcoded_solution_fails_simulation(self) -> None:
        """Verify that hardcoding only sample cases fails with WA when tested on simulated full inputs."""
        judge = JudgeRunner()

        full_simulation_test_suite = [
            {"input": "1 2\n", "output": "3\n"},
            {"input": "1000000000 1000000000\n", "output": "2000000000\n"},
            # Simulated hidden test case
            {"input": "45 55\n", "output": "100\n"},
        ]

        # Cheating solution that only handles the 2 sample cases
        hardcoded_cpp = r"""
#include <iostream>
using namespace std;
int main() {
    long long a, b;
    if (cin >> a >> b) {
        if (a == 1 && b == 2) cout << 3 << endl;
        else if (a == 1000000000 && b == 1000000000) cout << 2000000000 << endl;
        else cout << 0 << endl; // Fails on simulated hidden case
    }
    return 0;
}
"""

        res = judge.evaluate(
            code=hardcoded_cpp,
            sample_cases=full_simulation_test_suite,
            time_limit_sec=2.0,
            compiler_profile="g++ (C++20)",
        )

        assert res.verdict == "WA"
        assert res.test_results[0].verdict == "AC"
        assert res.test_results[1].verdict == "AC"
        assert res.test_results[2].verdict == "WA"
