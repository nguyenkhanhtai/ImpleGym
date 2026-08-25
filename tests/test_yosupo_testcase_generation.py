"""Test suite verifying testcase generation from info.toml and full test evaluation."""

from pathlib import Path

import pytest

from implegym.judge.runner import JudgeRunner
from implegym.problems.yosupo_syncer import YosupoSyncer


class TestYosupoTestcaseGeneration:
    """Test suite for info.toml-driven testcase generation and validation."""

    def test_params_header_generation(self, tmp_path: Path) -> None:
        """Verify that _generate_params_header writes accurate C++ macro constants."""
        syncer = YosupoSyncer(None)  # type: ignore
        params = {
            "MAX_N": 500_000,
            "MAX_Q": 500_000,
            "MAX_A": 1_000_000_000,
        }
        syncer._generate_params_header(tmp_path, params)

        params_file = tmp_path / "params.h"
        assert params_file.exists()
        content = params_file.read_text(encoding="utf-8")
        assert "MAX_N" in content and "500000" in content
        assert "MAX_Q" in content and "500000" in content
        assert "MAX_A" in content and "1000000000" in content

    def test_info_toml_testcase_generation_for_static_range_sum(self) -> None:
        """Verify that YosupoSyncer extracts and generates testcases from info.toml for static_range_sum."""
        prob_dir = Path("data") / "yosupo_repo" / "data_structure" / "static_range_sum"
        if not prob_dir.exists():
            pytest.skip("Local yosupo repository not present in data/yosupo_repo")

        syncer = YosupoSyncer(None)  # type: ignore
        params = {"MAX_N": 500_000, "MAX_Q": 500_000, "MAX_A": 1_000_000_000}

        testcases = syncer._generate_testcases_from_info_toml(prob_dir, params)
        assert len(testcases) > 0
        for tc in testcases:
            assert "in_path" in tc and Path(tc["in_path"]).exists()
            assert "out_path" in tc and Path(tc["out_path"]).exists()
            assert "name" in tc

        # Verify running correct solution against on-disk testcases produces 100% AC
        judge = JudgeRunner()
        fast_cpp = r"""
#include <iostream>
#include <vector>
using namespace std;
int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(NULL);
    int n, q;
    if (!(cin >> n >> q)) return 0;
    vector<long long> pref(n + 1, 0);
    for (int i = 0; i < n; ++i) {
        long long a; cin >> a;
        pref[i + 1] = pref[i] + a;
    }
    for (int i = 0; i < q; ++i) {
        int l, r; cin >> l >> r;
        cout << (pref[r] - pref[l]) << "\n";
    }
    return 0;
}
"""
        run_res = judge.evaluate(
            code=fast_cpp,
            testcases_dir=Path("data/testcases/static_range_sum"),
            time_limit_sec=5.0,
            compiler_profile="g++ (C++20)",
        )
        assert run_res.verdict == "AC"
        for tr in run_res.test_results:
            assert tr.verdict == "AC"

        # Verify dummy code fails with WA on generated testcases
        dummy_code = "// Dummy code that does nothing\nint main() { return 0; }\n"
        dummy_res = judge.evaluate(
            code=dummy_code,
            testcases_dir=Path("data/testcases/static_range_sum"),
            time_limit_sec=5.0,
            compiler_profile="g++ (C++20)",
        )
        assert dummy_res.verdict == "WA"
