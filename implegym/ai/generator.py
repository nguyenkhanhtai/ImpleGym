"""AI-driven composite problem synthesis, testcase generator execution, and self-testing pipeline."""

import json
import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from implegym.ai.client import OpenAIClient
from implegym.db.models import CustomProblem, Problem
from implegym.judge.compiler import CompilerManager
from implegym.judge.runner import JudgeRunner
from implegym.models.schemas import GenerateProblemRequest, ProblemResponseSchema


class ProblemGeneratorService:
    """Service that synthesizes novel CP problems, compiles test generators, and verifies solutions."""

    def __init__(
        self,
        session: AsyncSession,
        ai_client: Optional[OpenAIClient] = None,
        judge_runner: Optional[JudgeRunner] = None,
        compiler_manager: Optional[CompilerManager] = None,
    ) -> None:
        self.session = session
        self.ai = ai_client or OpenAIClient()
        self.compiler = compiler_manager or CompilerManager()
        self.judge = judge_runner or JudgeRunner(self.compiler)

    async def generate_problem(
        self, req: GenerateProblemRequest
    ) -> ProblemResponseSchema:
        """Generate a composite problem, execute test generator to produce tests, and verify model solution."""
        if not self.ai.is_configured:
            # Fallback deterministic generator template
            generated_dict = self._build_fallback_problem(req)
        else:
            prompt = self._build_generation_prompt(req)
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a Grandmaster Competitive Programmer and expert problem setter. "
                        "Design a high-quality, mathematically sound CP problem combining the two requested concepts. "
                        "You MUST provide: "
                        "1. A complete, bug-free C++20 model solution (solution_cpp). "
                        "2. A standalone C++ test generator (generator_cpp) that accepts an optional seed argument and outputs valid test inputs conforming strictly to the constraints. "
                        "Respond strictly in JSON matching the schema."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
            raw_json = await self.ai.chat_completion(
                messages=messages,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            generated_dict = self._parse_generated_json(raw_json, req)

        solution_cpp = generated_dict.get("solution_cpp", "")
        generator_cpp = generated_dict.get("generator_cpp", "")
        initial_samples = generated_dict.get("sample_cases", [])

        # 1. Synthesize additional testcases via generator execution + model solution
        all_test_cases = self._synthesize_full_testsuite(
            generator_code=generator_cpp,
            solution_code=solution_cpp,
            sample_cases=initial_samples,
            extra_test_count=3,
        )

        # 2. Self-test: Execute model solution against all generated test cases
        self_test_verdict = "AC"
        if solution_cpp and all_test_cases:
            validation = self.judge.evaluate(
                code=solution_cpp,
                sample_cases=all_test_cases,
                time_limit_sec=2.5,
                compiler_profile="g++ (C++20)",
            )
            self_test_verdict = validation.verdict

        # 3. Ensure unique slug
        raw_slug = generated_dict.get("slug", "custom_composite_problem")
        clean_slug = re.sub(r"[^a-zA-Z0-9_]", "_", raw_slug).lower().strip("_")
        unique_slug = f"ai_{clean_slug}"

        # 4. Save problem and verified testcases into PostgreSQL
        problem = Problem(
            slug=unique_slug,
            title=generated_dict.get("title", f"{req.topic_1} with {req.topic_2}"),
            category="Custom AI Composite",
            difficulty=req.target_difficulty,
            statement=generated_dict.get("statement", ""),
            input_format=generated_dict.get("input_format", ""),
            output_format=generated_dict.get("output_format", ""),
            constraints=generated_dict.get("constraints", ""),
            sample_cases=all_test_cases,
            time_limit=2.5,
            memory_limit_mb=1024,
            tags=[
                req.topic_1.lower().replace(" ", "_"),
                req.topic_2.lower().replace(" ", "_"),
                "ai_generated",
                f"self_test_{self_test_verdict.lower()}",
            ],
            source="gpt_generated",
        )
        self.session.add(problem)

        custom_record = CustomProblem(
            slug=unique_slug,
            title=problem.title,
            prompt_context=f"Combined: {req.topic_1} + {req.topic_2} | Self-Test: {self_test_verdict}",
            solution_cpp=solution_cpp,
            generator_cpp=generator_cpp,
            checker_cpp=generated_dict.get("checker_cpp", ""),
        )
        self.session.add(custom_record)

        await self.session.commit()
        await self.session.refresh(problem)

        return ProblemResponseSchema.model_validate(problem)

    def _synthesize_full_testsuite(
        self,
        generator_code: str,
        solution_code: str,
        sample_cases: List[Dict[str, str]],
        extra_test_count: int = 3,
    ) -> List[Dict[str, str]]:
        """Compile generator and solution, produce random inputs, and compute expected outputs."""
        testsuite: List[Dict[str, str]] = list(sample_cases)

        if not generator_code or not solution_code:
            return testsuite

        # Compile generator
        gen_comp = self.compiler.compile(generator_code, compiler_profile="g++ (C++20)")
        # Compile model solution
        sol_comp = self.compiler.compile(solution_code, compiler_profile="g++ (C++20)")

        if not gen_comp.success or not sol_comp.success or not gen_comp.executable_path or not sol_comp.executable_path:
            return testsuite

        # Generate inputs with various seeds
        seeds = [42, 1337, 2026, 99999, 777]
        for i in range(min(extra_test_count, len(seeds))):
            seed_val = str(seeds[i])
            try:
                # 1. Run generator
                gen_proc = subprocess.run(
                    [str(gen_comp.executable_path), seed_val],
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                    check=False,
                )
                test_in = gen_proc.stdout
                if not test_in.strip():
                    continue

                # 2. Run model solution to get ground-truth expected output
                sol_proc = subprocess.run(
                    [str(sol_comp.executable_path)],
                    input=test_in,
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                    check=False,
                )
                test_out = sol_proc.stdout
                if sol_proc.returncode == 0 and test_out.strip():
                    testsuite.append({
                        "input": test_in,
                        "output": test_out,
                    })
            except Exception:
                continue

        return testsuite

    def _build_generation_prompt(self, req: GenerateProblemRequest) -> str:
        """Create structured synthesis prompt asking for problem, test generator, and model solution."""
        return f"""
Synthesize a competitive programming problem combining:
1. Technique A: {req.topic_1}
2. Technique B: {req.topic_2}
Target Difficulty: {req.target_difficulty} / 10
Additional Instructions: {req.extra_instructions or 'None'}

Please respond strictly in JSON with keys:
- "title": (str) Problem title
- "slug": (str) snake_case identifier (e.g. fenwick_with_rmq)
- "statement": (str) Formal problem statement in Markdown with LaTeX math ($N$, $O(\\log N)$)
- "input_format": (str) Input format specifications
- "output_format": (str) Output format specifications
- "constraints": (str) Constraints in LaTeX
- "sample_cases": (list of dicts with "input" and "output") 1-2 realistic sample cases with explanations.
- "solution_cpp": (str) Complete, clean, 100% correct C++20 model solution.
- "generator_cpp": (str) Standalone C++ test generator that accepts an optional seed argument (e.g. `int seed = argc > 1 ? atoi(argv[1]) : 42;`) and prints a random valid test case to stdout conforming to constraints.
- "checker_cpp": (str) C++ comparator / checker code.
"""

    def _parse_generated_json(self, raw_json: str, req: GenerateProblemRequest) -> Dict[str, Any]:
        """Safely parse GPT generated problem dictionary."""
        try:
            return json.loads(raw_json)
        except Exception:
            return self._build_fallback_problem(req)

    def _build_fallback_problem(self, req: GenerateProblemRequest) -> Dict[str, Any]:
        """Generate deterministic fallback composite problem with working generator and solution."""
        slug_base = f"{req.topic_1}_{req.topic_2}".lower().replace(" ", "_")
        return {
            "title": f"Range Operations with {req.topic_1} and {req.topic_2}",
            "slug": slug_base,
            "statement": (
                f"You are given an array of $N$ elements. Process $Q$ queries requiring an optimal "
                f"combination of **{req.topic_1}** and **{req.topic_2}**.\n\n"
                f"- `0 p x`: Update element at index $p$ with value $x$.\n"
                f"- `1 l r`: Compute the range sum from $l$ to $r-1$."
            ),
            "input_format": "$N$ $Q$\n$a_0$ $a_1$ ... $a_{N-1}$\nQuery 1\n...\nQuery Q",
            "output_format": "Output results for all type 1 queries.",
            "constraints": "$1 \\le N, Q \\le 10^5$, $0 \\le a_i, x \\le 10^9$, $0 \\le l < r \\le N$",
            "sample_cases": [
                {
                    "input": "5 3\n1 2 3 4 5\n1 0 5\n0 2 10\n1 0 5\n",
                    "output": "15\n22\n",
                }
            ],
            "solution_cpp": (
                "#include <iostream>\n#include <vector>\nusing namespace std;\n"
                "struct Fenwick { vector<long long> t; Fenwick(int n): t(n+1, 0) {} "
                "void add(int i, long long v){ for(++i; i<t.size(); i+=i&-i) t[i]+=v; } "
                "long long sum(int i){ long long s=0; for(; i>0; i-=i&-i) s+=t[i]; return s; } "
                "long long query(int l, int r){ return sum(r) - sum(l); } };\n"
                "int main() {\n"
                "    ios_base::sync_with_stdio(false); cin.tie(nullptr);\n"
                "    int n, q; if(!(cin >> n >> q)) return 0;\n"
                "    vector<long long> a(n);\n"
                "    Fenwick bit(n);\n"
                "    for(int i=0; i<n; ++i){ cin >> a[i]; bit.add(i, a[i]); }\n"
                "    while(q--){\n"
                "        int type; cin >> type;\n"
                "        if(type == 0){\n"
                "            int p; long long x; cin >> p >> x;\n"
                "            bit.add(p, x - a[p]);\n"
                "            a[p] = x;\n"
                "        } else {\n"
                "            int l, r; cin >> l >> r;\n"
                "            cout << bit.query(l, r) << '\\n';\n"
                "        }\n"
                "    }\n"
                "    return 0;\n"
                "}\n"
            ),
            "generator_cpp": (
                "#include <iostream>\n#include <random>\n#include <cstdlib>\nusing namespace std;\n"
                "int main(int argc, char** argv) {\n"
                "    int seed = (argc > 1) ? atoi(argv[1]) : 42;\n"
                "    mt19937_64 rng(seed);\n"
                "    int n = 5, q = 3;\n"
                "    cout << n << ' ' << q << '\\n';\n"
                "    for(int i=0; i<n; ++i) cout << (rng() % 10 + 1) << (i + 1 == n ? '\\n' : ' ');\n"
                "    for(int i=0; i<q; ++i){\n"
                "        int type = rng() % 2;\n"
                "        if(type == 0) cout << 0 << ' ' << (rng() % n) << ' ' << (rng() % 20 + 1) << '\\n';\n"
                "        else { int l = rng() % n, r = rng() % (n - l) + l + 1; cout << 1 << ' ' << l << ' ' << r << '\\n'; }\n"
                "    }\n"
                "    return 0;\n"
                "}\n"
            ),
            "checker_cpp": "",
        }
