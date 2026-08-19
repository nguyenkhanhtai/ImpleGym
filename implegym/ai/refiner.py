"""AI-powered competitive programming code refinement engine."""

import json
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from implegym.ai.client import OpenAIClient
from implegym.db.models import AIReview, Submission
from implegym.models.schemas import AIReviewResponseSchema, AIReviewSuggestion


class CodeRefinerService:
    """Service that analyzes CP code submissions and generates actionable advice."""

    def __init__(self, session: AsyncSession, ai_client: Optional[OpenAIClient] = None) -> None:
        self.session = session
        self.ai = ai_client or OpenAIClient()

    async def refine_submission(self, submission_id: int) -> AIReviewResponseSchema:
        """Analyze a submission and produce structured CP refinement suggestions."""
        # Check existing review
        stmt = (
            select(Submission)
            .where(Submission.id == submission_id)
            .options(selectinload(Submission.problem), selectinload(Submission.ai_review))
        )
        res = await self.session.execute(stmt)
        submission = res.scalar_one_or_none()
        if not submission:
            raise ValueError(f"Submission #{submission_id} not found")

        if submission.ai_review:
            return AIReviewResponseSchema(
                id=submission.ai_review.id,
                submission_id=submission.id,
                feedback_markdown=submission.ai_review.feedback_markdown,
                suggestions=[
                    AIReviewSuggestion(**s) for s in submission.ai_review.suggestions
                ],
                model_used=submission.ai_review.model_used,
                created_at=submission.ai_review.created_at,
            )

        problem = submission.problem
        prompt = self._build_refine_prompt(submission, problem)

        if not self.ai.is_configured:
            # Generate heuristic offline review if OpenAI API key is missing
            feedback, suggestions = self._build_offline_fallback(submission)
        else:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a Grandmaster Competitive Programmer and Senior Software Engineer. "
                        "Review the user's competitive programming submission code. "
                        "Focus on: (1) Constant factor optimization & cache locality, "
                        "(2) Clean CP idioms & templates, (3) Memory layout & pointer overhead, "
                        "(4) Edge cases & undefined behavior. "
                        "Respond strictly in JSON format matching the requested schema."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
            raw_json = await self.ai.chat_completion(
                messages=messages,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            feedback, suggestions = self._parse_ai_response(raw_json)

        # Store in database
        review = AIReview(
            submission_id=submission.id,
            feedback_markdown=feedback,
            suggestions=suggestions,
            model_used=self.ai.model if self.ai.is_configured else "offline-heuristic",
        )
        self.session.add(review)
        await self.session.commit()
        await self.session.refresh(review)

        return AIReviewResponseSchema(
            id=review.id,
            submission_id=submission.id,
            feedback_markdown=review.feedback_markdown,
            suggestions=[AIReviewSuggestion(**s) for s in review.suggestions],
            model_used=review.model_used,
            created_at=review.created_at,
        )

    def _build_refine_prompt(self, submission: Submission, problem: Any) -> str:
        """Construct structured refinement prompt for GPT."""
        return f"""
Problem: {problem.title} ({problem.category}, Difficulty: {problem.difficulty}/10)
Statement:
{problem.statement}

Constraints:
{problem.constraints}

User Submission:
Language: {submission.language}
Compiler: {submission.compiler_profile} (Flags: {submission.compiler_flags})
Verdict: {submission.verdict}
Execution Time: {submission.exec_time_ms} ms

Code:
```cpp
{submission.code}
```

Please output JSON with keys:
- "feedback_markdown": Detailed comprehensive markdown review of the implementation.
- "suggestions": A list of objects with:
  - "category": ("Performance" | "CP Idiom" | "Memory Layout" | "Edge Case" | "Clean Code")
  - "title": Short title
  - "detail": Actionable advice
  - "code_diff": Optional suggested code snippet or diff
"""

    def _parse_ai_response(self, raw_json: str) -> tuple[str, List[Dict[str, Any]]]:
        """Safely parse GPT JSON response."""
        try:
            data = json.loads(raw_json)
            feedback = data.get("feedback_markdown", "No feedback provided.")
            suggestions = data.get("suggestions", [])
            return feedback, suggestions
        except Exception:
            return raw_json, []

    def _build_offline_fallback(self, submission: Submission) -> tuple[str, List[Dict[str, Any]]]:
        """Generate offline static CP advice when OpenAI key is not set."""
        suggestions = [
            {
                "category": "Performance",
                "title": "Fast I/O & Buffer Optimization",
                "detail": (
                    "Ensure `std::cin.tie(nullptr); std::ios_base::sync_with_stdio(false);` "
                    "is at the start of `main()`, and prefer `\\n` over `std::endl` to prevent stream flushes."
                ),
                "code_diff": "std::cin.tie(nullptr)->sync_with_stdio(false);",
            },
            {
                "category": "Memory Layout",
                "title": "Avoid Pointer-heavy Dynamic Allocation",
                "detail": (
                    "In tree and graph problems, prefer static contiguous arrays (flat indexing) "
                    "over dynamic `new` or nested `std::vector` to maximize L1/L2 CPU cache hits."
                ),
                "code_diff": None,
            },
        ]
        feedback = f"""### Competitive Programming Analysis ({submission.verdict})
- **Compiler Profile**: `{submission.compiler_profile}`
- **Optimization Flags**: `{submission.compiler_flags}`
- **Execution Time**: `{submission.exec_time_ms or 0.0} ms`

> Note: To get real-time AI code reviews from ChatGPT, set `OPENAI_API_KEY` in your `.env` file."""
        return feedback, suggestions
