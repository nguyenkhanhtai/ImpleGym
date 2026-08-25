import asyncio
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from implegym.config import settings
from implegym.db.models import Problem

logger = logging.getLogger("implegym.problems.yosupo")

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore


# Heuristic implementation difficulty mapping baseline for Yosupo topics
CATEGORY_DIFFICULTY_BASELINE: dict[str, int] = {
    "sample": 1,
    "data_structure": 5,
    "datastructure": 5,
    "tree": 6,
    "graph": 6,
    "math": 5,
    "number_theory": 5,
    "enumerative_combinatorics": 6,
    "linear_algebra": 6,
    "string": 6,
    "geo": 7,
    "geometry": 7,
    "matrix": 6,
    "polynomial": 7,
    "convolution": 7,
    "set_power_series": 8,
    "big_integer": 6,
    "other": 5,
}

# Specific curated difficulty overrides for well-known library-checker problems
KNOWN_PROBLEM_DIFFICULTIES: dict[str, int] = {
    "aplusb": 1,
    "many_aplusb": 2,
    "associative_array": 2,
    "unionfind": 3,
    "staticrmq": 3,
    "static_range_sum": 2,
    "point_add_range_sum": 4,
    "point_set_range_composite": 4,
    "range_affine_range_sum": 5,
    "range_chmin_chmax_add_range_sum": 8,
    "range_kth_smallest": 6,
    "lca": 5,
    "tree_diameter": 4,
    "jump_on_tree": 5,
    "vertex_add_path_sum": 6,
    "vertex_set_path_composite": 6,
    "dynamic_tree_vertex_add_path_sum": 7,
    "dynamic_tree_vertex_set_path_composite": 7,
    "dynamic_tree_subtree_add_subtree_sum": 10,
    "dynamic_sequence_range_affine_range_sum": 8,
    "scc": 4,
    "two_sat": 4,
    "shortest_path": 4,
    "bipartitematching": 5,
    "general_matching": 9,
    "general_weighted_matching": 10,
    "maximum_flow": 6,
    "min_cost_b_flow": 8,
    "suffixarray": 6,
    "zalgorithm": 5,
    "run_enumerate": 8,
    "lyndon_factorization": 7,
    "convolution_mod": 7,
    "convolution_mod_1000000007": 8,
    "multipoint_evaluation": 9,
    "polynomial_taylor_shift": 8,
}


class YosupoSyncer:
    """Clones, parses, and synchronizes problems from the official Yosupo repository."""

    OFFICIAL_REPO_URL = "https://github.com/yosupo06/library-checker-problems.git"

    def __init__(self, session: AsyncSession, repo_dir: Path | None = None) -> None:
        self.session = session
        self.repo_dir = repo_dir or settings.yosupo_problems_dir or (Path("data") / "yosupo_repo")

    def clone_or_pull_repo(self) -> bool:
        """Clone the repository if missing, or pull latest changes if already present."""
        self.repo_dir.parent.mkdir(parents=True, exist_ok=True)
        if not (self.repo_dir / ".git").exists():
            cmd = ["git", "clone", "--depth", "1", self.OFFICIAL_REPO_URL, str(self.repo_dir)]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            return res.returncode == 0
        else:
            cmd = ["git", "-C", str(self.repo_dir), "pull"]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            return res.returncode == 0

    def parse_problem_directory(
        self, category_name: str, problem_dir: Path, generate_tests: bool = True
    ) -> dict[str, Any] | None:
        """Parse a single Yosupo problem directory containing info.toml, task.md, and sample cases."""
        info_toml = problem_dir / "info.toml"
        task_md = problem_dir / "task.md"

        if not info_toml.exists() or not task_md.exists():
            return None

        slug = problem_dir.name
        title = slug.replace("_", " ").title()
        time_limit = 2.0
        params: dict[str, Any] = {}

        # 1. Parse info.toml
        try:
            with open(info_toml, "rb") as f:
                info_data = tomllib.load(f)
                title = info_data.get("title", title)
                time_limit = float(info_data.get("timelimit", 2.0))
                params = info_data.get("params", {})
        except Exception:
            pass

        # 2. Parse task.md
        raw_markdown = task_md.read_text(encoding="utf-8", errors="ignore")
        statement, input_fmt, output_fmt, constraints = self._extract_markdown_sections(
            raw_markdown, params
        )

        # 3. Extract sample cases and conditionally generate testcases from info.toml
        sample_cases = self._extract_sample_cases(problem_dir, raw_markdown)[:2]
        if generate_tests:
            generated_tests = self._generate_testcases_from_info_toml(problem_dir, params)
            all_testcases = sample_cases + generated_tests
        else:
            all_testcases = sample_cases

        # 4. Compute Difficulty (1..10)
        difficulty = self._calculate_difficulty(slug, category_name, problem_dir)

        category_display = category_name.replace("_", " ").title()

        return {
            "slug": slug,
            "title": title,
            "category": category_display,
            "difficulty": difficulty,
            "statement": statement,
            "input_format": input_fmt,
            "output_format": output_fmt,
            "constraints": constraints,
            "sample_cases": all_testcases if all_testcases else sample_cases,
            "time_limit": time_limit,
            "memory_limit_mb": 1024,
            "tags": [category_name, slug],
            "source": "yosupo_official",
        }

    async def sync_all_problems(
        self,
        progress_callback: Any | None = None,
        tracker: Any | None = None,
        force_regenerate_tests: bool = False,
    ) -> int:
        """Scan full repository and synchronize all problems into the database with progress tracking and test caching."""
        from implegym.problems.sync_manager import sync_progress_tracker

        active_tracker = tracker or sync_progress_tracker

        active_tracker.start(total=0, message="Updating official Yosupo repository...")
        if progress_callback:
            try:
                res = progress_callback(active_tracker.get_state().model_dump(mode="json"))
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

        if not self.repo_dir.exists() or not (self.repo_dir / ".git").exists():
            self.clone_or_pull_repo()
        else:
            self.clone_or_pull_repo()

        if not self.repo_dir.exists():
            active_tracker.fail("Failed to clone or locate Yosupo repository.")
            return 0

        # Phase 1: Pre-scan and discover all candidate directories
        active_tracker.update(
            stage="scanning", message="Scanning repository for problem definitions..."
        )
        if progress_callback:
            try:
                res = progress_callback(active_tracker.get_state().model_dump(mode="json"))
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

        problem_candidates: list[tuple[str, Path]] = []
        for root, _dirs, files in os.walk(self.repo_dir):
            if "info.toml" in files and "task.md" in files:
                prob_path = Path(root)
                rel_parts = prob_path.relative_to(self.repo_dir).parts
                category = rel_parts[0] if len(rel_parts) > 1 else "general"
                problem_candidates.append((category, prob_path))

        total_count = len(problem_candidates)
        active_tracker.update(
            stage="syncing_problems",
            total=total_count,
            current=0,
            synced_count=0,
            message=f"Found {total_count} problems. Syncing definitions...",
        )
        if progress_callback:
            try:
                res = progress_callback(active_tracker.get_state().model_dump(mode="json"))
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

        synced_count = 0
        for idx, (category, prob_path) in enumerate(problem_candidates):
            if active_tracker.is_cancelled():
                logger.warning("Problem synchronization cancelled by user.")
                active_tracker.update(stage="cancelled", message="Synchronization cancelled by user.")
                break

            slug = prob_path.name
            active_tracker.update(
                current=idx + 1,
                current_slug=slug,
                current_category=category,
                message=f"Processing {slug} ({idx + 1}/{total_count})...",
            )
            if progress_callback:
                try:
                    res = progress_callback(active_tracker.get_state().model_dump(mode="json"))
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    pass

            try:
                # Check if problem already exists and has cached test cases
                stmt = select(Problem).where(Problem.slug == slug)
                res_stmt = await self.session.execute(stmt)
                existing = res_stmt.scalar_one_or_none()

                needs_test_generation = (
                    force_regenerate_tests
                    or existing is None
                    or not existing.sample_cases
                    or len(existing.sample_cases) == 0
                )

                prob_data = self.parse_problem_directory(
                    category, prob_path, generate_tests=needs_test_generation
                )
                if not prob_data:
                    continue

                if existing:
                    existing.title = prob_data["title"]
                    existing.category = prob_data["category"]
                    # Preserve user customized difficulty across synchronizations
                    if not getattr(existing, "is_difficulty_customized", False):
                        existing.difficulty = prob_data["difficulty"]
                    existing.statement = prob_data["statement"]
                    existing.input_format = prob_data["input_format"]
                    existing.output_format = prob_data["output_format"]
                    existing.constraints = prob_data["constraints"]
                    if needs_test_generation and prob_data["sample_cases"]:
                        existing.sample_cases = prob_data["sample_cases"]
                    existing.time_limit = prob_data["time_limit"]
                else:
                    new_problem = Problem(**prob_data)
                    self.session.add(new_problem)

                synced_count += 1
                # Commit incrementally so problems are visible and persisted immediately
                await self.session.commit()
                active_tracker.update(synced_count=synced_count)
            except Exception as e:
                logger.error(f"Error parsing problem {slug}: {e}")

        if not active_tracker.is_cancelled():
            active_tracker.complete(
                synced_count=synced_count,
                message=f"Successfully synchronized {synced_count} problems from official Yosupo repository!",
            )
        if progress_callback:
            try:
                res = progress_callback(active_tracker.get_state().model_dump(mode="json"))
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass
        return synced_count

    async def sync_problem(self, slug: str) -> dict[str, Any] | None:
        """Find a specific problem by slug, parse and regenerate all testcases, and update database."""
        if not self.repo_dir.exists():
            self.clone_or_pull_repo()

        if not self.repo_dir.exists():
            return None

        target_path: Path | None = None
        target_category: str = "general"
        for root, _dirs, files in os.walk(self.repo_dir):
            if "info.toml" in files and "task.md" in files:
                p_path = Path(root)
                if p_path.name == slug:
                    target_path = p_path
                    rel_parts = target_path.relative_to(self.repo_dir).parts
                    target_category = rel_parts[0] if len(rel_parts) > 1 else "general"
                    break

        if not target_path:
            return None

        prob_data = self.parse_problem_directory(target_category, target_path)
        if not prob_data:
            return None

        stmt = select(Problem).where(Problem.slug == prob_data["slug"])
        res = await self.session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.title = prob_data["title"]
            existing.category = prob_data["category"]
            if not getattr(existing, "is_difficulty_customized", False):
                existing.difficulty = prob_data["difficulty"]
            existing.statement = prob_data["statement"]
            existing.input_format = prob_data["input_format"]
            existing.output_format = prob_data["output_format"]
            existing.constraints = prob_data["constraints"]
            if prob_data["sample_cases"]:
                existing.sample_cases = prob_data["sample_cases"]
            existing.time_limit = prob_data["time_limit"]
        else:
            new_problem = Problem(**prob_data)
            self.session.add(new_problem)

        await self.session.commit()
        return prob_data

    def _extract_markdown_sections(
        self, raw_md: str, params: dict[str, Any]
    ) -> tuple[str, str, str, str]:
        """Extract clean statement and substitute param macros."""
        text = raw_md

        # 1. Substitute @{param.XYZ} macros with real numbers from info.toml
        for k, v in params.items():
            formatted_val = f"{v:,}".replace(",", "\\,") if isinstance(v, (int, float)) else str(v)
            text = text.replace(f"@{{param.{k}}}", formatted_val)

        # 2. Extract English block if bilingual
        if "@{lang.en}" in text:
            # Strip out Japanese section between @{lang.ja} and @{lang.end} or next section
            text = re.sub(r"@\{lang\.ja\}[\s\S]*?(@\{lang\.end\}|$)", "", text)
            text = text.replace("@{lang.en}", "").replace("@{lang.end}", "")

        # 3. Clean section header keywords
        text = text.replace("@{keyword.statement}", "Problem Statement")
        text = text.replace("@{keyword.constraints}", "Constraints")
        text = text.replace("@{keyword.input}", "Input Format")
        text = text.replace("@{keyword.output}", "Output Format")

        # 4. Remove sample sections from statement markdown to prevent duplicated header
        text = re.sub(r"##\s*@?\{?keyword\.sample\}?[\s\S]*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"##\s*Sample\s*Cases[\s\S]*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"##\s*Samples[\s\S]*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"@\{example\.[^}]+\}", "", text)

        # 5. Convert tildes code blocks ~~~ to standard ```
        text = text.replace("~~~", "```")

        # Extract constraints section if marked
        constraints = ""
        c_match = re.search(r"##\s*Constraints", text, re.IGNORECASE)
        if c_match:
            c_start = c_match.end()
            c_end = text.find("##", c_start)
            constraints = text[c_start:c_end].strip() if c_end != -1 else text[c_start:].strip()

        return text.strip(), "", "", constraints

    def _extract_sample_cases(self, problem_dir: Path, raw_md: str) -> list[dict[str, str]]:
        """Extract sample cases from problem directory or gen folder, generating outputs if needed."""
        samples: list[dict[str, str]] = []
        gen_dir = problem_dir / "gen"

        # Check problem_dir and gen_dir for example_*.in and example_*.out
        search_dirs = [problem_dir]
        if gen_dir.exists():
            search_dirs.append(gen_dir)

        for s_dir in search_dirs:
            for in_file in sorted(s_dir.glob("example_*.in")):
                out_file = in_file.with_suffix(".out")
                in_content = in_file.read_text(encoding="utf-8", errors="ignore").strip()
                out_content = (
                    out_file.read_text(encoding="utf-8", errors="ignore").strip()
                    if out_file.exists()
                    else ""
                )

                # If output is missing, generate it via reference solution
                if not out_content and in_content:
                    out_content = self._generate_sample_output(problem_dir, in_file)

                if in_content:
                    samples.append(
                        {
                            "input": in_content + "\n",
                            "output": (out_content + "\n") if out_content else "",
                        }
                    )

        return samples

    def _generate_params_header(self, problem_dir: Path, params: dict[str, Any]) -> None:
        """Write params.h header file containing problem parameter macro constants."""
        params_file = problem_dir / "params.h"
        lines = ["#pragma once\n"]
        for k, v in params.items():
            if isinstance(v, (int, float)):
                lines.append(f"#define {k} (long long){v}\n")
            elif isinstance(v, str):
                lines.append(f'#define {k} "{v}"\n')
        try:
            params_file.write_text("".join(lines), encoding="utf-8")
        except Exception:
            pass

    def _generate_testcases_from_info_toml(
        self, problem_dir: Path, params: dict[str, Any]
    ) -> list[dict[str, str]]:
        """Generate full test cases on the fly and delete compiled binaries/temporary files immediately to save disk space."""
        info_toml = problem_dir / "info.toml"
        if not info_toml.exists():
            return []

        try:
            with open(info_toml, "rb") as f:
                info_data = tomllib.load(f)
        except Exception:
            return []

        tests_config = info_data.get("tests", [])
        if not tests_config:
            return []

        created_files: list[Path] = []
        generated_tests: list[dict[str, str]] = []

        try:
            # 1. Write params.h if params exist
            params_file = problem_dir / "params.h"
            if params:
                self._generate_params_header(problem_dir, params)
                created_files.append(params_file)

            # 2. Locate and compile reference solution
            sol_dir = problem_dir / "sol"
            if not sol_dir.exists():
                return []

            cpp_sols = list(sol_dir.glob("correct.cpp")) + list(sol_dir.glob("main.cpp"))
            if not cpp_sols:
                return []
            sol_file = cpp_sols[0]
            sol_exe = sol_file.with_suffix(".exe")

            common_include = problem_dir.parent.parent / "common"
            if not sol_exe.exists():
                try:
                    cmd = ["g++", "-O3", "-std=c++17"]
                    if common_include.exists():
                        cmd.extend(["-I", str(common_include)])
                    cmd.extend(["-I", str(problem_dir), str(sol_file), "-o", str(sol_exe)])
                    subprocess.run(cmd, capture_output=True, timeout=15)
                    created_files.append(sol_exe)
                except Exception:
                    pass

            if not sol_exe.exists():
                return []

            gen_dir = problem_dir / "gen"
            if not gen_dir.exists():
                return []

            MAX_GENERATED_TESTS = 2
            MAX_TEST_SIZE_BYTES = 12 * 1024 * 1024  # 12 MB max per test (prevents SQLite INT_MAX overflow while supporting Yosupo standard tests)

            for test_entry in tests_config:
                if len(generated_tests) >= MAX_GENERATED_TESTS:
                    break

                test_name = test_entry.get("name", "")
                if not test_name.endswith(".cpp"):
                    continue

                gen_file = gen_dir / test_name
                if not gen_file.exists():
                    continue

                gen_exe = gen_file.with_suffix(".exe")
                if not gen_exe.exists():
                    try:
                        cmd = ["g++", "-O3", "-std=c++17"]
                        if common_include.exists():
                            cmd.extend(["-I", str(common_include)])
                        cmd.extend(
                            [
                                "-I",
                                str(problem_dir),
                                "-I",
                                str(gen_dir),
                                str(gen_file),
                                "-o",
                                str(gen_exe),
                            ]
                        )
                        subprocess.run(cmd, capture_output=True, timeout=15)
                        created_files.append(gen_exe)
                    except Exception:
                        pass

                if not gen_exe.exists():
                    continue

                num_to_generate = min(int(test_entry.get("number", 1)), 2)
                for seed in range(1, num_to_generate + 1):
                    if len(generated_tests) >= MAX_GENERATED_TESTS:
                        break
                    try:
                        # Run generator with seed
                        gen_res = subprocess.run(
                            [str(gen_exe), str(seed)], capture_output=True, timeout=10
                        )
                        if gen_res.returncode != 0 or not gen_res.stdout:
                            continue
                        input_data = gen_res.stdout
                        if len(input_data) > MAX_TEST_SIZE_BYTES:
                            continue

                        # Run reference solution to get expected output
                        sol_res = subprocess.run(
                            [str(sol_exe)], input=input_data, capture_output=True, timeout=15
                        )
                        if sol_res.returncode != 0 or not sol_res.stdout or len(sol_res.stdout) > MAX_TEST_SIZE_BYTES:
                            continue

                        in_text = input_data.decode("utf-8", errors="ignore").strip()
                        out_text = sol_res.stdout.decode("utf-8", errors="ignore").strip()
                        if in_text and out_text:
                            generated_tests.append(
                                {
                                    "name": f"{gen_file.stem}_{seed:02d}",
                                    "input": in_text + "\n",
                                    "output": out_text + "\n",
                                }
                            )
                    except Exception:
                        continue
        finally:
            # Clean up all compiled executables and temporary params headers to save disk space
            for f_path in created_files:
                if f_path.exists():
                    try:
                        f_path.unlink(missing_ok=True)
                    except Exception:
                        pass

        return generated_tests

    def _generate_sample_output(self, problem_dir: Path, in_file: Path) -> str:
        """Run reference solution to generate missing sample output."""
        sol_dir = problem_dir / "sol"
        if not sol_dir.exists():
            return ""

        cpp_candidates = (
            list(sol_dir.glob("correct.cpp"))
            + list(sol_dir.glob("main.cpp"))
            + list(sol_dir.glob("*.cpp"))
        )
        if cpp_candidates:
            cpp_file = cpp_candidates[0]
            exe_file = cpp_file.with_suffix(".exe")
            common_include = problem_dir.parent.parent / "common"

            if not exe_file.exists():
                try:
                    cmd = ["g++", "-O3", "-std=c++17"]
                    if common_include.exists():
                        cmd.extend(["-I", str(common_include)])
                    cmd.extend([str(cpp_file), "-o", str(exe_file)])
                    subprocess.run(cmd, capture_output=True, timeout=15)
                except Exception:
                    pass

            if exe_file.exists():
                try:
                    res = subprocess.run(
                        [str(exe_file)],
                        input=in_file.read_bytes(),
                        capture_output=True,
                        timeout=10,
                    )
                    if res.returncode == 0:
                        out_text = res.stdout.decode("utf-8", errors="ignore").strip()
                        if out_text:
                            out_file = in_file.with_suffix(".out")
                            out_file.write_text(out_text + "\n", encoding="utf-8")
                            return out_text
                except Exception:
                    pass

        # Python fallback
        py_candidates = (
            list(sol_dir.glob("correct.py"))
            + list(sol_dir.glob("main.py"))
            + list(sol_dir.glob("*.py"))
        )
        if py_candidates:
            py_file = py_candidates[0]
            try:
                res = subprocess.run(
                    [sys.executable, str(py_file)],
                    input=in_file.read_bytes(),
                    capture_output=True,
                    timeout=10,
                )
                if res.returncode == 0:
                    out_text = res.stdout.decode("utf-8", errors="ignore").strip()
                    if out_text:
                        out_file = in_file.with_suffix(".out")
                        out_file.write_text(out_text + "\n", encoding="utf-8")
                        return out_text
            except Exception:
                pass

        return ""

    def _calculate_difficulty(self, slug: str, category: str, prob_dir: Path) -> int:
        """Assign an implementation difficulty rating (1..10)."""
        if slug in KNOWN_PROBLEM_DIFFICULTIES:
            return KNOWN_PROBLEM_DIFFICULTIES[slug]

        base = CATEGORY_DIFFICULTY_BASELINE.get(category.lower(), 5)
        # Check reference solution complexity
        sol_file = prob_dir / "sol" / "correct.cpp"
        if sol_file.exists():
            line_count = len(sol_file.read_text(encoding="utf-8", errors="ignore").splitlines())
            if line_count > 150:
                base = min(10, base + 2)
            elif line_count > 80:
                base = min(10, base + 1)
        return max(1, min(10, base))


if __name__ == "__main__":
    import argparse
    import asyncio

    from implegym.db.database import get_db_context

    parser = argparse.ArgumentParser(
        description="Generate testcases from info.toml and sync Yosupo problems."
    )
    parser.add_argument(
        "slug",
        nargs="?",
        default=None,
        help="Problem slug to generate testcases for (e.g. static_range_sum)",
    )
    parser.add_argument(
        "--all", action="store_true", help="Sync and generate testcases for all problems"
    )
    args = parser.parse_args()

    async def run():
        async with get_db_context() as session:
            syncer = YosupoSyncer(session)
            if args.slug:
                print(f"[*] Generating testcases for problem: {args.slug}...")
                res = await syncer.sync_problem(args.slug)
                if res:
                    print(
                        f"[+] Success! Generated {len(res.get('sample_cases', []))} testcases for {args.slug}"
                    )
                else:
                    print(f"[-] Problem {args.slug} not found.")
            elif args.all:
                print("[*] Syncing and generating testcases for all problems...")
                count = await syncer.sync_all_problems()
                print(f"[+] Completed! Synced {count} problems.")
            else:
                parser.print_help()

    asyncio.run(run())
