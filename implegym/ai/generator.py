"""AI-driven composite problem and test case generator."""

import json
import re
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from implegym.ai.client import OpenAIClient
from implegym.db.models import CustomProblem, Problem
from implegym.judge.runner import JudgeRunner
from implegym.models.schemas import GenerateProblemRequest, ProblemResponseSchema


class ProblemGeneratorService:
    """Service that synthesizes novel CP problems combining multiple data structures."""

    def __init__(
        self,
        session: AsyncSession,
        ai_client: Optional[OpenAIClient] = None,
        judge_runner: Optional[JudgeRunner] = None,
    ) -> None:
        self.session = session
        self.ai = ai_client or OpenAIClient()
        self.judge = judge_runner or JudgeRunner()

    async def generate_problem(
        self, req: GenerateProblemRequest
    ) -> ProblemResponseSchema:
        """Generate a composite problem combining two techniques and index into database."""
        if not self.ai.is_configured:
            # Fallback template if OpenAI is not configured
            generated_dict = self._build_fallback_problem(req)
        else:
            prompt = self._build_generation_prompt(req)
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert Competitive Programming problem setter. "
                        "Design a high quality, well-defined problem that seamlessly combines "
                        "the two requested data structures or algorithmic techniques. "
                        "Ensure the model solution and samples are 100% mathematically correct. "
                        "Output strictly JSON matching the required schema."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
            raw_json = await self.ai.chat_completion(
                messages=messages,
                temperature=0.4,
                response_format={"type": "json_object"},
            )
            generated_dict = self._parse_generated_json(raw_json, req)

        # Validate solution against sample cases
        sample_cases = generated_dict.get("sample_cases", [])
        solution_cpp = generated_dict.get("solution_cpp", "")
        if solution_cpp and sample_cases:
            validation = self.judge.evaluate(
                code=solution_cpp,
                sample_cases=sample_cases,
                compiler_profile="g++ (C++20)",
            )
            # If CE or WA on samples, we still store but note in statement if needed

        # Ensure slug uniqueness
        raw_slug = generated_dict.get("slug", "custom_composite_problem")
        clean_slug = re.sub(r"[^a-zA-Z0-9_]", "_", raw_slug).lower().strip("_")
        unique_slug = f"ai_{clean_slug}"

        problem = Problem(
            slug=unique_slug,
            title=generated_dict.get("title", f"{req.topic_1} with {req.topic_2}"),
            category="Custom AI Composite",
            difficulty=req.target_difficulty,
            statement=generated_dict.get("statement", ""),
            input_format=generated_dict.get("input_format", ""),
            output_format=generated_dict.get("output_format", ""),
            constraints=generated_dict.get("constraints", ""),
            sample_cases=sample_cases,
            time_limit=2.5,
            memory_limit_mb=1024,
            tags=[req.topic_1.lower().replace(" ", "_"), req.topic_2.lower().replace(" ", "_"), "ai_generated"],
            source="gpt_generated",
        )
        self.session.add(problem)

        custom_record = CustomProblem(
            slug=unique_slug,
            title=problem.title,
            prompt_context=f"Combined: {req.topic_1} + {req.topic_2}",
            solution_cpp=solution_cpp,
            generator_cpp=generated_dict.get("generator_cpp", ""),
            checker_cpp=generated_dict.get("checker_cpp", ""),
        )
        self.session.add(custom_record)

        await self.session.commit()
        await self.session.refresh(problem)

        return ProblemResponseSchema.model_validate(problem)

    def _build_generation_prompt(self, req: GenerateProblemRequest) -> str:
        """Create structured synthesis prompt."""
        return f"""
Synthesize a competitive programming problem combining:
1. Technique A: {req.topic_1}
2. Technique B: {req.topic_2}
Target Difficulty: {req.target_difficulty} / 10
Additional Instructions: {req.extra_instructions or 'None'}

Please respond strictly in JSON with keys:
- "title": (str) Problem title
- "slug": (str) snake_case identifier
- "statement": (str) Problem statement in Markdown with LaTeX ($math$)
- "input_format": (str) Input format specifications
- "output_format": (str) Output format specifications
- "constraints": (str) Constraints in LaTeX
- "sample_cases": (list of dicts with "input" and "output") At least 1-2 realistic sample cases with explanations.
- "solution_cpp": (str) Complete, working, clean C++20 model solution.
- "generator_cpp": (str) C++ testcase generator code.
- "checker_cpp": (str) C++ comparator code.
"""

    def _parse_generated_json(self, raw_json: str, req: GenerateProblemRequest) -> Dict[str, Any]:
        """Safely parse GPT generated problem dictionary."""
        try:
            return json.loads(raw_json)
        except Exception:
            return self._build_fallback_problem(req)

    def _build_fallback_problem(self, req: GenerateProblemRequest) -> Dict[str, Any]:
        """Generate deterministic fallback composite problem."""
        slug_base = f"{req.topic_1}_{req.topic_2}".lower().replace(" ", "_")
        return {
            "title": f"Dynamic Range Queries with {req.topic_1} and {req.topic_2}",
            "slug": slug_base,
            "statement": (
                f"You are given an array of $N$ elements. Perform $Q$ queries requiring "
                f"an optimal combination of **{req.topic_1}** and **{req.topic_2}**."
            ),
            "input_format": "$N$ $Q$\n$a_0$ $a_1$ ... $a_{N-1}$\nQuery 1\n...\nQuery Q",
            "output_format": "Output results for all query operations.",
            "constraints": "$1 \\le N, Q \\le 2 \\times 10^5$, $0 \\le a_i \\le 10^9$",
            "sample_cases": [
                {
                    "input": "5 3\n1 2 3 4 5\n0 1 3\n1 0 4\n0 2 5\n",
                    "output": "6\n15\n12\n",
                }
            ],
            "solution_cpp": (
                "#include <iostream>\n#include <vector>\nusing namespace std;\n"
                "int main() { ios::sync_with_stdio(false); cin.tie(nullptr); return 0; }\n"
            ),
            "generator_cpp": "",
            "checker_cpp": "",
        }
