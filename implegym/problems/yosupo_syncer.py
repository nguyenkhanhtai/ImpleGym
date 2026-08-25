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
        self,
        category_name: str,
        problem_dir: Path,
        generate_tests: bool = True,
        max_tests: int = 10,
        force_regenerate: bool = False,
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

        # 3. Extract lightweight sample cases and write to disk
        sample_cases = self._extract_sample_cases(problem_dir, raw_markdown)[:2]
        testcases_dir_path = Path("data") / "testcases" / slug
        testcases_dir_path.mkdir(parents=True, exist_ok=True)

        # Save official sample cases to disk as 00_sample_*.in and .out
        for idx, sc in enumerate(sample_cases):
            ex_in = testcases_dir_path / f"00_sample_{idx:02d}.in"
            ex_out = testcases_dir_path / f"00_sample_{idx:02d}.out"
            if not ex_in.exists() or force_regenerate:
                ex_in.write_text(sc.get("input", ""), encoding="utf-8")
            if not ex_out.exists() or force_regenerate:
                ex_out.write_text(sc.get("output", ""), encoding="utf-8")

        # 4. Generate additional tests on disk incrementally
        if generate_tests:
            self._generate_testcases_from_info_toml(
                problem_dir,
                params,
                max_tests=max_tests,
                target_dir=testcases_dir_path,
                force=force_regenerate,
            )

        # 5. Compute Difficulty (1..10)
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
            "sample_cases": sample_cases,
            "testcases_dir": str(testcases_dir_path).replace("\\", "/"),
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
        max_tests: int = 10,
    ) -> int:
        """Scan full repository and synchronize all problems into the database with progress tracking and test caching."""
        from implegym.problems.sync_manager import sync_progress_tracker

        active_tracker = tracker or sync_progress_tracker
        active_tracker.start(
            total=1,
            message="Initializing Yosupo repository...",
        )

        if not self.repo_dir.exists():
            self.clone_or_pull_repo()

        if not self.repo_dir.exists():
            active_tracker.fail("Failed to clone or locate official Yosupo repository")
            return 0

        # Scan all directories containing info.toml and task.md
        problem_dirs: list[tuple[str, Path]] = []
        for root, _dirs, files in os.walk(self.repo_dir):
            if "info.toml" in files and "task.md" in files:
                p_path = Path(root)
                rel_parts = p_path.relative_to(self.repo_dir).parts
                category = rel_parts[0] if len(rel_parts) > 1 else "general"
                problem_dirs.append((category, p_path))

        total_count = len(problem_dirs)
        active_tracker.update(total=total_count, message=f"Discovered {total_count} problems.")
        if progress_callback:
            try:
                res = progress_callback(active_tracker.get_state().model_dump(mode="json"))
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

        synced_count = 0
        for idx, (category, prob_path) in enumerate(problem_dirs):
            if active_tracker.is_cancelled():
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
                    category,
                    prob_path,
                    generate_tests=needs_test_generation,
                    max_tests=max_tests,
                    force_regenerate=force_regenerate_tests,
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
                    if prob_data.get("sample_cases"):
                        existing.sample_cases = prob_data["sample_cases"]
                    if prob_data.get("testcases_dir"):
                        existing.testcases_dir = prob_data["testcases_dir"]
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

    async def sync_problem(
        self,
        slug: str,
        generate_tests: bool = True,
        max_tests: int = 10,
        force_regenerate: bool = False,
    ) -> dict[str, Any] | None:
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

        prob_data = self.parse_problem_directory(
            target_category,
            target_path,
            generate_tests=generate_tests,
            max_tests=max_tests,
            force_regenerate=force_regenerate,
        )
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
            if prob_data.get("sample_cases"):
                existing.sample_cases = prob_data["sample_cases"]
            if prob_data.get("testcases_dir"):
                existing.testcases_dir = prob_data["testcases_dir"]
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
        text = text.replace("@{keyword.sample}", "Sample")

        statement_part = text
        input_fmt = ""
        output_fmt = ""
        constraints = ""

        # Extract subsections
        if "## Constraints" in text:
            parts = text.split("## Constraints", 1)
            statement_part = parts[0].strip()
            rest = parts[1]
            if "## Input" in rest or "## Output" in rest:
                sub_parts = re.split(r"##\s+(?:Input|Output)", rest, 1)
                constraints = sub_parts[0].strip()
            else:
                constraints = rest.strip()

        if "## Input" in text:
            in_part = text.split("## Input", 1)[1]
            if "## Output" in in_part:
                input_fmt = in_part.split("## Output", 1)[0].strip()
            else:
                input_fmt = in_part.strip()

        if "## Output" in text:
            out_part = text.split("## Output", 1)[1]
            if "## Sample" in out_part:
                output_fmt = out_part.split("## Sample", 1)[0].strip()
            else:
                output_fmt = out_part.strip()

        return statement_part, input_fmt, output_fmt, constraints

    def _extract_sample_cases(
        self, problem_dir: Path, raw_md: str
    ) -> list[dict[str, str]]:
        """Extract sample cases from example_*.in/out files or task.md."""
        sample_cases: list[dict[str, str]] = []

        # 1. Try finding example_*.in and example_*.out in problem directory
        gen_dir = problem_dir / "gen"
        in_files: list[Path] = []
        if gen_dir.exists():
            in_files = sorted(list(gen_dir.glob("example_*.in")) + list(gen_dir.glob("example-*.in")) + list(gen_dir.glob("example.in")))

        if not in_files:
            in_files = sorted(list(problem_dir.glob("example_*.in")) + list(problem_dir.glob("example.in")))

        if in_files:
            for in_f in in_files:
                out_f = in_f.with_suffix(".out")
                if not out_f.exists():
                    out_f = in_f.parent / f"{in_f.stem}.out"
                
                in_content = in_f.read_text(encoding="utf-8", errors="ignore").strip()
                out_content = ""
                if out_f.exists():
                    out_content = out_f.read_text(encoding="utf-8", errors="ignore").strip()
                else:
                    out_content = self._generate_sample_output(problem_dir, in_f)

                if in_content:
                    sample_cases.append({
                        "name": in_f.stem,
                        "input": in_content + "\n",
                        "output": out_content + "\n" if out_content else "",
                    })

        # 2. If no files, fallback to regex parse markdown ```blocks
        if not sample_cases:
            matches = re.findall(r"```(?:example|input|output)?\s*\n([\s\S]*?)\n```", raw_md)
            if len(matches) >= 2:
                for i in range(0, len(matches) - 1, 2):
                    sample_cases.append({
                        "name": f"sample_{i // 2 + 1}",
                        "input": matches[i].strip() + "\n",
                        "output": matches[i + 1].strip() + "\n",
                    })

        return sample_cases

    def _generate_params_header(self, problem_dir: Path, params: dict[str, Any]) -> None:
        """Write params.h if missing and required by generators or solutions."""
        if not params:
            return
        params_file = problem_dir / "params.h"
        try:
            lines = ["#pragma once\n"]
            for k, v in params.items():
                if isinstance(v, int):
                    lines.append(f"const long long {k} = {v}LL;\n")
                elif isinstance(v, float):
                    lines.append(f"const double {k} = {v};\n")
                elif isinstance(v, str):
                    lines.append(f'const char* {k} = "{v}";\n')
            params_file.write_text("".join(lines), encoding="utf-8")
        except Exception:
            pass

    def _generate_testcases_from_info_toml(
        self,
        problem_dir: Path,
        params: dict[str, Any],
        max_tests: int = 10,
        target_dir: Path | None = None,
        force: bool = False,
    ) -> list[dict[str, str]]:
        """Compile generators and reference solutions to create full judge testcases on disk incrementally."""
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

        slug = problem_dir.name
        out_dir = target_dir or (Path("data") / "testcases" / slug)
        out_dir.mkdir(parents=True, exist_ok=True)

        generated_tests: list[dict[str, str]] = []
        created_files: list[Path] = []
        sol_exe: Path | None = None

        try:
            gen_dir = problem_dir / "gen"
            if not gen_dir.exists():
                return []

            MAX_GENERATED_TESTS = max_tests
            valid_cpp_tests = [t for t in tests_config if t.get("name", "").endswith(".cpp")]
            per_generator_count = max(2, (max_tests + len(valid_cpp_tests) - 1) // max(1, len(valid_cpp_tests)))

            for test_entry in tests_config:
                if len(generated_tests) >= MAX_GENERATED_TESTS:
                    break

                test_name = test_entry.get("name", "")
                if not test_name.endswith(".cpp"):
                    continue

                gen_file = gen_dir / test_name
                if not gen_file.exists():
                    continue

                num_to_generate = min(int(test_entry.get("number", 1)), per_generator_count)
                for seed in range(1, num_to_generate + 1):
                    if len(generated_tests) >= MAX_GENERATED_TESTS:
                        break

                    tc_stem = f"{gen_file.stem}_{seed:02d}"
                    in_path = out_dir / f"{tc_stem}.in"
                    out_path = out_dir / f"{tc_stem}.out"

                    # Incremental check: if files already exist on disk and not force, skip generation!
                    if in_path.exists() and out_path.exists() and in_path.stat().st_size > 0 and not force:
                        generated_tests.append({
                            "name": tc_stem,
                            "in_path": str(in_path),
                            "out_path": str(out_path),
                        })
                        continue

                    # Needs generation: compile sol and gen lazily if not compiled yet
                    if sol_exe is None or not sol_exe.exists():
                        self._generate_params_header(problem_dir, params)
                        params_h = problem_dir / "params.h"
                        if params_h.exists():
                            created_files.append(params_h)

                        sol_dir = problem_dir / "sol"
                        if not sol_dir.exists():
                            return []
                        cpp_sols = list(sol_dir.glob("correct.cpp")) or list(sol_dir.glob("*.cpp"))
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

                    if not sol_exe or not sol_exe.exists():
                        continue

                    gen_exe = gen_file.with_suffix(".exe")
                    if not gen_exe.exists():
                        try:
                            cmd = ["g++", "-O3", "-std=c++17"]
                            common_include = problem_dir.parent.parent / "common"
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

                    try:
                        # Run generator directly writing to in_path file on disk
                        with open(in_path, "wb") as f_in:
                            gen_res = subprocess.run(
                                [str(gen_exe), str(seed)], stdout=f_in, capture_output=False, timeout=10
                            )
                        if gen_res.returncode != 0 or not in_path.exists() or in_path.stat().st_size == 0:
                            in_path.unlink(missing_ok=True)
                            continue

                        # Run reference solution directly streaming stdin from in_path and writing to out_path
                        with open(in_path, "rb") as f_in, open(out_path, "wb") as f_out:
                            sol_res = subprocess.run(
                                [str(sol_exe)], stdin=f_in, stdout=f_out, capture_output=False, timeout=15
                            )
                        if sol_res.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
                            in_path.unlink(missing_ok=True)
                            out_path.unlink(missing_ok=True)
                            continue

                        generated_tests.append(
                            {
                                "name": tc_stem,
                                "in_path": str(in_path),
                                "out_path": str(out_path),
                            }
                        )
                    except Exception:
                        in_path.unlink(missing_ok=True)
                        out_path.unlink(missing_ok=True)
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
