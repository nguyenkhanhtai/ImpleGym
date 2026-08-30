import asyncio
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from implegym.config import settings
from implegym.db.models import Problem

logger = logging.getLogger("implegym.problems.syncer")

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore


DEFAULT_DIFFICULTY: int = 5

CATEGORY_DIFFICULTY_BASELINE: dict[str, int] = {
    "sample": 1,
    "test": 2,
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
    "big_integer": 5,
    "other": 5,
}

KNOWN_PROBLEM_DIFFICULTIES: dict[str, int] = CATEGORY_DIFFICULTY_BASELINE


class ProblemSyncer:
    """Parses and seeds problems from the local problems repository."""

    def __init__(self, session: AsyncSession, repo_dir: Path | None = None) -> None:
        self.session = session
        self.repo_dir = (
            repo_dir
            or settings.problems_base_dir
            or (
                Path("data") / "yosupo_repo"
                if (Path("data") / "yosupo_repo").exists()
                else Path("data") / "problems_repo"
            )
        )

    def parse_problem_directory(
        self,
        category_name: str,
        problem_dir: Path,
        generate_tests: bool = False,
        max_tests: int | None = None,
        force_regenerate: bool = False,
    ) -> dict[str, Any] | None:
        """Parse a single problem directory containing info.toml, task.md, and sample cases."""
        info_toml = problem_dir / "info.toml"
        task_md = problem_dir / "task.md"

        if not info_toml.exists() or not task_md.exists():
            return None

        slug = problem_dir.name
        title = slug.replace("_", " ").title()
        time_limit = 2.0
        parsed_difficulty: int | None = None

        # 1. Parse info.toml
        try:
            with open(info_toml, "rb") as f:
                info_data = tomllib.load(f)
                title = info_data.get("title", title)
                time_limit = float(info_data.get("timelimit", 2.0))
                params = info_data.get("params", {})
                if "difficulty" in info_data:
                    try:
                        parsed_difficulty = int(info_data["difficulty"])
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass

        # 2. Parse task.md
        raw_markdown = task_md.read_text(encoding="utf-8", errors="ignore")
        statement, input_fmt, output_fmt, constraints = self._extract_markdown_sections(
            raw_markdown, params
        )

        # 3. Extract lightweight sample cases and write to disk
        sample_cases = self._extract_sample_cases(
            problem_dir, raw_markdown, params=params, time_limit=time_limit
        )
        testcases_dir_path = Path("data") / "testcases" / slug
        testcases_dir_path.mkdir(parents=True, exist_ok=True)

        # Save official sample cases to disk as 00_sample_*.in and .out
        for idx, sc in enumerate(sample_cases):
            ex_in = testcases_dir_path / f"00_sample_{idx:02d}.in"
            ex_out = testcases_dir_path / f"00_sample_{idx:02d}.out"
            if not ex_in.exists() or force_regenerate:
                ex_in.write_text(sc.get("input", ""), encoding="utf-8")
            if not ex_out.exists() or force_regenerate or ex_out.stat().st_size == 0:
                ex_out.write_text(sc.get("output", ""), encoding="utf-8")

        # 4. Generate additional full judge tests on disk only when requested (e.g. on submission)
        if generate_tests:
            self._generate_testcases_from_info_toml(
                problem_dir,
                params,
                max_tests=max_tests,
                target_dir=testcases_dir_path,
                force=force_regenerate,
            )

        # 5. Compute Difficulty (1..10)
        difficulty = self._calculate_difficulty(
            slug, category_name, problem_dir, explicit_difficulty=parsed_difficulty
        )

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
        max_tests: int | None = None,
    ) -> int:
        """Scan all problems, parse them, extract sample outputs, and insert into DB."""
        from implegym.problems.sync_manager import sync_progress_tracker

        active_tracker = tracker or sync_progress_tracker
        active_tracker.start(
            total=1,
            message="Initializing problems repository...",
        )

        if not self.repo_dir.exists():
            active_tracker.fail("Local problems repository directory not found")
            return 0

        # Scan all directories containing info.toml and task.md
        problem_dirs: list[tuple[str, Path]] = []
        for root, _dirs, files in os.walk(self.repo_dir):
            if "info.toml" in files and "task.md" in files:
                p_path = Path(root)
                rel_parts = p_path.relative_to(self.repo_dir).parts
                category = rel_parts[0] if len(rel_parts) > 1 else "general"
                if category.lower() == "test":
                    continue
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

                # Syncing only generates sample cases (never full test generator suites unless force)
                prob_data = self.parse_problem_directory(
                    category,
                    prob_path,
                    generate_tests=force_regenerate_tests,
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
                message=f"Successfully synchronized {synced_count} problems from official problems repository!",
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
        max_tests: int | None = None,
        force_regenerate: bool = False,
    ) -> dict[str, Any] | None:
        """Find a specific problem by slug, parse and regenerate all testcases, and update database."""
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
        text = text.replace("@{keyword.input}", "Input")
        text = text.replace("@{keyword.output}", "Output")
        text = text.replace("@{keyword.sample}", "Sample")

        # Strip sample macro tags like @{example.example_00} from statement
        text = re.sub(r"@\{example\.[^}]+\}", "", text)

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
                sub_parts = re.split(r"##\s+(?:Input|Output)", rest, maxsplit=1)
                constraints = sub_parts[0].strip()
            else:
                constraints = rest.strip()
        elif "## Input" in text:
            statement_part = text.split("## Input", 1)[0].strip()
        elif "## Output" in text:
            statement_part = text.split("## Output", 1)[0].strip()

        if "## Input" in text:
            in_part = text.split("## Input", 1)[1]
            if "## Output" in in_part:
                input_fmt = in_part.split("## Output", 1)[0].strip()
            elif "## Sample" in in_part:
                input_fmt = in_part.split("## Sample", 1)[0].strip()
            else:
                input_fmt = in_part.strip()

        if "## Output" in text:
            out_part = text.split("## Output", 1)[1]
            if "## Sample" in out_part:
                output_fmt = out_part.split("## Sample", 1)[0].strip()
            else:
                output_fmt = out_part.strip()

        return statement_part, input_fmt, output_fmt, constraints

    def _compile_cpp_executable(
        self,
        src_file: Path,
        problem_dir: Path,
        params: dict[str, Any],
        tmp_dir: Path,
        exe_name: str = "program.exe",
        extra_include_dir: Path | None = None,
    ) -> Path | None:
        """Compile a C++ file in an isolated build sandbox with params.h and common/ includes."""
        prob_shadow = tmp_dir / "prob"
        if not prob_shadow.exists():
            try:
                shutil.copytree(
                    problem_dir,
                    prob_shadow,
                    symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "*.in", "*.out"),
                )
            except Exception:
                prob_shadow.mkdir(parents=True, exist_ok=True)

        # Ensure params.h exists inside shadow directory
        params_h = prob_shadow / "params.h"
        if not params_h.exists() and params:
            try:
                lines = ["#pragma once\n"]
                for k, v in params.items():
                    if isinstance(v, int):
                        lines.append(f"const long long {k} = {v}LL;\n")
                    elif isinstance(v, float):
                        lines.append(f"const double {k} = {v};\n")
                    elif isinstance(v, str):
                        lines.append(f'const char* {k} = "{v}";\n')
                params_h.write_text("".join(lines), encoding="utf-8")
            except Exception:
                pass

        exe_path = tmp_dir / exe_name
        common_include = self.repo_dir / "common"

        # Determine path to source file inside shadow directory if possible
        try:
            rel_src = src_file.relative_to(problem_dir)
            shadow_src = prob_shadow / rel_src
            target_src = shadow_src if shadow_src.exists() else src_file
        except Exception:
            target_src = src_file

        for std in ["-std=c++17", "-std=c++20", "-std=c++23"]:
            cmd = ["g++", "-O2", std]
            if common_include.exists():
                cmd.extend(["-I", str(common_include)])
            cmd.extend(["-I", str(prob_shadow), "-I", str(problem_dir)])
            if extra_include_dir and extra_include_dir.exists():
                cmd.extend(["-I", str(extra_include_dir)])
            if target_src.parent.exists():
                cmd.extend(["-I", str(target_src.parent)])
            cmd.extend([str(target_src), "-o", str(exe_path)])

            try:
                res = subprocess.run(cmd, capture_output=True, timeout=25)
                if res.returncode == 0 and exe_path.exists():
                    return exe_path
            except Exception:
                pass

        return None

    def _extract_sample_cases(
        self,
        problem_dir: Path,
        raw_md: str,
        params: dict[str, Any] | None = None,
        time_limit: float = 2.0,
    ) -> list[dict[str, str]]:
        """Extract sample cases and generate missing sample outputs using the reference solution."""
        sample_cases: list[dict[str, str]] = []
        slug = problem_dir.name
        cached_sample_dir = Path("data") / "testcases" / slug

        # Auto-load params and timelimit from info.toml if not provided
        if params is None:
            info_toml = problem_dir / "info.toml"
            if info_toml.exists():
                try:
                    with open(info_toml, "rb") as f:
                        info_data = tomllib.load(f)
                        params = info_data.get("params", {})
                        if time_limit == 2.0 and "timelimit" in info_data:
                            time_limit = float(info_data["timelimit"])
                except Exception:
                    params = {}

        # 1. Try finding example_*.in in gen directory or problem directory
        gen_dir = problem_dir / "gen"
        in_files: list[Path] = []
        if gen_dir.exists():
            in_files = sorted(
                [
                    *gen_dir.glob("example_*.in"),
                    *gen_dir.glob("example-*.in"),
                    *gen_dir.glob("example.in"),
                ]
            )

        if not in_files:
            in_files = sorted(
                [
                    *problem_dir.glob("example_*.in"),
                    *problem_dir.glob("example.in"),
                ]
            )

        if in_files:
            sol_exe: Path | None = None
            tmp_build_dir: tempfile.TemporaryDirectory | None = None

            try:
                for idx, in_f in enumerate(in_files):
                    in_content = in_f.read_text(encoding="utf-8", errors="ignore").strip()
                    if not in_content:
                        continue

                    out_content = ""
                    out_f = in_f.with_suffix(".out")
                    cached_out_f = cached_sample_dir / f"00_sample_{idx:02d}.out"

                    # Check if official .out exists alongside .in
                    if out_f.exists():
                        out_content = out_f.read_text(encoding="utf-8", errors="ignore").strip()
                    # Check if already generated in testcases cached directory
                    elif cached_out_f.exists() and cached_out_f.stat().st_size > 0:
                        out_content = cached_out_f.read_text(
                            encoding="utf-8", errors="ignore"
                        ).strip()
                    # Generate output using reference solution
                    else:
                        if tmp_build_dir is None:
                            tmp_build_dir = tempfile.TemporaryDirectory()
                            sol_dir = problem_dir / "sol"
                            cpp_sols = (
                                (
                                    list(sol_dir.glob("correct.cpp"))
                                    + list(sol_dir.glob("main.cpp"))
                                    + list(sol_dir.glob("*.cpp"))
                                )
                                if sol_dir.exists()
                                else []
                            )
                            if cpp_sols:
                                sol_exe = self._compile_cpp_executable(
                                    cpp_sols[0],
                                    problem_dir,
                                    params or {},
                                    Path(tmp_build_dir.name),
                                    exe_name="sol.exe",
                                )

                        if sol_exe and sol_exe.exists():
                            try:
                                timeout_sec = max(10, int(time_limit) + 5)
                                run_res = subprocess.run(
                                    [str(sol_exe)],
                                    input=in_f.read_bytes(),
                                    capture_output=True,
                                    timeout=timeout_sec,
                                )
                                if run_res.returncode == 0:
                                    out_content = run_res.stdout.decode(
                                        "utf-8", errors="ignore"
                                    ).strip()
                            except Exception as e:
                                logger.debug(f"Failed running solution for sample {in_f.name}: {e}")

                        # Python solution fallback
                        if not out_content:
                            sol_dir = problem_dir / "sol"
                            py_sols = list(sol_dir.glob("*.py")) if sol_dir.exists() else []
                            if py_sols:
                                try:
                                    run_res = subprocess.run(
                                        [sys.executable, str(py_sols[0])],
                                        input=in_f.read_bytes(),
                                        capture_output=True,
                                        timeout=max(10, int(time_limit) + 5),
                                    )
                                    if run_res.returncode == 0:
                                        out_content = run_res.stdout.decode(
                                            "utf-8", errors="ignore"
                                        ).strip()
                                except Exception:
                                    pass

                    sample_cases.append(
                        {
                            "name": in_f.stem,
                            "input": in_content + "\n",
                            "output": out_content + "\n" if out_content else "",
                        }
                    )
            finally:
                if tmp_build_dir is not None:
                    try:
                        tmp_build_dir.cleanup()
                    except Exception:
                        pass

        # 2. Fallback to parsing markdown code blocks if no files found on disk
        if not sample_cases:
            matches = re.findall(r"```(?:example|input|output)?\s*\n([\s\S]*?)\n```", raw_md)
            if len(matches) >= 2:
                for i in range(0, len(matches) - 1, 2):
                    sample_cases.append(
                        {
                            "name": f"sample_{i // 2 + 1}",
                            "input": matches[i].strip() + "\n",
                            "output": matches[i + 1].strip() + "\n",
                        }
                    )

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
        max_tests: int | None = None,
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

        # Collect expected valid test filenames for this problem
        valid_filenames: set[str] = set()
        for test_entry in tests_config:
            test_name = test_entry.get("name", "")
            if not test_name.endswith(".cpp"):
                continue
            gen_stem = Path(test_name).stem
            num_to_gen = int(test_entry.get("number", 1))
            for seed in range(1, num_to_gen + 1):
                valid_filenames.add(f"{gen_stem}_{seed:02d}.in")
                valid_filenames.add(f"{gen_stem}_{seed:02d}.out")

        # Purge any unexpected, stale, or orphan files that do not belong to info.toml
        for disk_file in list(out_dir.glob("*")):
            if disk_file.is_file():
                # Allow official sample cases
                if disk_file.name.startswith(("00_sample_", "example_")) and disk_file.suffix in (
                    ".in",
                    ".out",
                ):
                    continue
                if disk_file.name not in valid_filenames:
                    try:
                        disk_file.unlink(missing_ok=True)
                    except Exception:
                        pass

        generated_tests: list[dict[str, str]] = []
        gen_dir = problem_dir / "gen"
        if not gen_dir.exists():
            return []

        with tempfile.TemporaryDirectory() as tmp_build_dir_name:
            tmp_build_dir = Path(tmp_build_dir_name)
            sol_exe: Path | None = None

            sol_dir = problem_dir / "sol"
            cpp_sols = (
                (
                    list(sol_dir.glob("correct.cpp"))
                    + list(sol_dir.glob("main.cpp"))
                    + list(sol_dir.glob("*.cpp"))
                )
                if sol_dir.exists()
                else []
            )

            compiled_gens: dict[str, Path] = {}

            for test_entry in tests_config:
                if max_tests is not None and len(generated_tests) >= max_tests:
                    break

                test_name = test_entry.get("name", "")
                if not test_name.endswith(".cpp"):
                    continue

                gen_file = gen_dir / test_name
                if not gen_file.exists():
                    continue

                # Generate exact number specified in info.toml for this generator
                num_to_generate = int(test_entry.get("number", 1))
                for seed in range(1, num_to_generate + 1):
                    if max_tests is not None and len(generated_tests) >= max_tests:
                        break

                    tc_stem = f"{gen_file.stem}_{seed:02d}"
                    in_path = out_dir / f"{tc_stem}.in"
                    out_path = out_dir / f"{tc_stem}.out"

                    # Incremental check: if files already exist on disk and not force, skip generation!
                    if (
                        in_path.exists()
                        and out_path.exists()
                        and in_path.stat().st_size > 0
                        and not force
                    ):
                        generated_tests.append(
                            {
                                "name": tc_stem,
                                "in_path": str(in_path),
                                "out_path": str(out_path),
                            }
                        )
                        continue

                    # Compile solution lazily in sandbox if not already compiled
                    if sol_exe is None and cpp_sols:
                        sol_exe = self._compile_cpp_executable(
                            cpp_sols[0],
                            problem_dir,
                            params,
                            tmp_build_dir,
                            exe_name="sol.exe",
                        )

                    if not sol_exe or not sol_exe.exists():
                        continue

                    # Compile generator lazily in sandbox if not already compiled
                    if test_name not in compiled_gens:
                        g_exe = self._compile_cpp_executable(
                            gen_file,
                            problem_dir,
                            params,
                            tmp_build_dir,
                            exe_name=f"gen_{gen_file.stem}.exe",
                            extra_include_dir=gen_dir,
                        )
                        if g_exe:
                            compiled_gens[test_name] = g_exe

                    gen_exe = compiled_gens.get(test_name)
                    if not gen_exe or not gen_exe.exists():
                        continue

                    try:
                        # Run generator directly writing to in_path file on disk
                        with open(in_path, "wb") as f_in:
                            gen_res = subprocess.run(
                                [str(gen_exe), str(seed)],
                                stdout=f_in,
                                capture_output=False,
                                timeout=15,
                            )
                        if (
                            gen_res.returncode != 0
                            or not in_path.exists()
                            or in_path.stat().st_size == 0
                        ):
                            in_path.unlink(missing_ok=True)
                            continue

                        # Run reference solution directly streaming stdin from in_path and writing to out_path
                        with open(in_path, "rb") as f_in, open(out_path, "wb") as f_out:
                            sol_res = subprocess.run(
                                [str(sol_exe)],
                                stdin=f_in,
                                stdout=f_out,
                                capture_output=False,
                                timeout=25,
                            )
                        if (
                            sol_res.returncode != 0
                            or not out_path.exists()
                            or out_path.stat().st_size == 0
                        ):
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

            # Ensure any sample cases present in out_dir also have non-empty .out outputs
            for sample_in in out_dir.glob("00_sample_*.in"):
                sample_out = sample_in.with_suffix(".out")
                if (
                    (not sample_out.exists() or sample_out.stat().st_size == 0)
                    and sol_exe
                    and sol_exe.exists()
                ):
                    try:
                        with open(sample_in, "rb") as f_in, open(sample_out, "wb") as f_out:
                            subprocess.run([str(sol_exe)], stdin=f_in, stdout=f_out, timeout=15)
                    except Exception:
                        pass

        return generated_tests

    def _calculate_difficulty(
        self,
        slug: str,
        category: str,
        prob_dir: Path,
        explicit_difficulty: int | None = None,
    ) -> int:
        """Extract implementation difficulty directly from info.toml, or fallback to default value."""
        # 1. If explicit difficulty passed or in info.toml, use it directly
        if explicit_difficulty is not None and 1 <= explicit_difficulty <= 10:
            return explicit_difficulty

        # 2. Extract directly from info.toml if present
        info_toml = prob_dir / "info.toml"
        if info_toml.exists():
            try:
                with open(info_toml, "rb") as f:
                    info_data = tomllib.load(f)
                    if "difficulty" in info_data:
                        diff = int(info_data["difficulty"])
                        if 1 <= diff <= 10:
                            return diff
            except Exception:
                pass

        # 3. Fallback to category baseline or standard default (5)
        return CATEGORY_DIFFICULTY_BASELINE.get(category.lower(), DEFAULT_DIFFICULTY)


if __name__ == "__main__":
    import argparse
    import asyncio

    from implegym.db.database import init_db, session_scope

    parser = argparse.ArgumentParser(
        description="Generate testcases from info.toml and sync problems."
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

    async def run() -> None:
        await init_db()
        async with session_scope() as session:
            syncer = ProblemSyncer(session)
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


# Backward compatibility alias
YosupoSyncer = ProblemSyncer
