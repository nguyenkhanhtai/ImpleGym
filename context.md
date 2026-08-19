# ImpleGym - Session Context & Development Journal

This document tracks all project requirements, architectural decisions, prompt history, implementation logs, execution steps, and verification results across AI sessions.

---

## 1. Project Overview & Objective

**ImpleGym** is a competitive programming implementation training gym built on top of the `yosupo06/library-checker-problems` dataset. It empowers competitive programmers to drill implementation speed and accuracy under realistic timing constraints with local judging, AI-assisted code reviews, and GPT-powered problem synthesis.

### Key Functional Requirements
1. **Problem Source**: Integration with [yosupo06/library-checker-problems](https://github.com/yosupo06/library-checker-problems).
2. **Local Judging & Live Stopwatch**: Local automated judging engine supporting multiple compilers (GCC C++17/20/23, Clang++, Python). Live stopwatch tracks elapsed time until the first `AC` verdict.
3. **Gaussian & Skewed Difficulty Sampler**: Sample problems on a 1–10 difficulty scale with customizable normal distribution (balanced, left-skewed for easier, right-skewed for harder) and topic filtering.
4. **Interactive Problem Explorer**: Manual problem catalog with search, category filtering, difficulty sliders, and solved/attempted status.
5. **Persistent History & Analytics (PostgreSQL)**: Permanent records of practice sessions and code submissions with telemetry (memory, runtime, test verdicts, time-to-AC).
6. **Per-Submission AI Code Refinement**: OpenAI-powered competitive programming tips (constant-factor optimization, cache locality, memory layout, clean idioms, corner cases) available for each submission.
7. **AI Problem & Test Synthesizer**: GPT-driven composite problem generator creating novel problems by combining multiple data structure techniques with testlib generators and model solutions.
8. **Modern Automated Testing & DevOps**:
   - Playwright E2E browser automation.
   - Hypothesis property-based testing for sampler invariants.
   - Testcontainers for ephemeral PostgreSQL instances during test runs.
   - Multi-stage Dockerfile, Docker Compose with health checks, and GitHub Actions CI.

---

## 2. Interaction & Requirement History

### Session 1: Requirements Definition & System Architecture

#### User Prompt 1
> "Trong ImpleGym, này tôi muốn xây dựng một framework như sau:
> - Sử dụng repo https://github.com/yosupo06/library-checker-problems để làm danh sách problem...
> - Backend server chấm submission, đếm giờ, dừng lại khi AC.
> - Sampling theo độ khó 1->10 theo phân phối chuẩn, có tùy chọn lệch trái/phải.
> - Code refinement bằng API ChatGPT.
> - Bộ tạo problem và test dựa trên GPT kết hợp data structures từ yosupo."

#### Agent Actions
- Inspected workspace directory and verified toolchain (`Python 3.14.3`, `g++ 15.2.0`, `git 2.53.0`).
- Authored initial `implementation_plan.md` defining core architecture, indexer, sampler, local judge, AI refiner, problem generator, and web interface.

---

#### User Prompt 2
> "I don't want to use sqlite, i want to use postgresql. Also, when I submit, allow me to change the version of compiler"

#### Agent Actions
- Replaced SQLite with **PostgreSQL** using SQLAlchemy Async ORM and `asyncpg`.
- Designed multi-compiler support allowing users to choose compiler standards on submission:
  - GCC C++17, C++20, C++23
  - Clang++ C++20, C++23
  - Python 3 / PyPy 3
  - Custom optimization flags (`-O2`, `-O3`, `-march=native`, `-fsanitize=undefined`) and compiler binaries.
- Updated `implementation_plan.md`.

---

#### User Prompt 3
> "Add testing to the system, DevOps stuff"

#### Agent Actions
- Added comprehensive Testing Suite (unit, integration, statistical distribution tests, compiler matrix) and DevOps infrastructure:
  - Multi-stage `Dockerfile`
  - `docker-compose.yml` (API service + PostgreSQL 16 with health checks)
  - GitHub Actions CI workflow (`.github/workflows/ci.yml`)
  - `Makefile` and `pyproject.toml` configuration.
- Updated `implementation_plan.md`.

---

#### User Prompt 4
> "can we use more modern testing systems? I don't like manual testing like this"

#### Agent Actions
- Upgraded the testing architecture to modern automated testing paradigms:
  - **Playwright E2E (`pytest-playwright`)**: Headless browser automation testing the full UI workflow, KaTeX rendering, live stopwatch, WebSocket streaming, and code submissions.
  - **Hypothesis Property-Based Testing**: Mathematical fuzzing of sampler bounds $[1, 10]$ and skewness invariants.
  - **Differential Fuzz Testing**: Automated judge verification comparing candidate solutions against testlib generators and model solutions.
  - **Testcontainers (`testcontainers[postgres]`)**: Ephemeral PostgreSQL containers created on-demand for zero-config isolated testing.
  - **Pytest-Benchmark**: Latency and throughput regression testing.
- Updated `implementation_plan.md`.

---

#### User Prompt 5
> "ALso, make the problem líst as well, because I'd like to choose some problems myself as well. There should be records of every time I code. Within each submission, there would be refinement button to ask for some tips and advice from gpt in terms of cp."

#### Agent Actions
- Added **Interactive Problem Explorer** tab for manual search, category filters, difficulty range, and solved status.
- Added **Persistent History & Analytics** table for tracking all past sessions, time-to-AC metrics, code snapshots, and compiler flags.
- Added **Per-Submission AI Refinement button** triggering CP-specific GPT feedback directly on any submission card.
- Updated `implementation_plan.md`.

---

#### User Prompt 6 & 7
> "Create a context.md. This is personal, every time I ask you, and you answer me, record my question and what you've done in the context.md, record that for the next AI session."
> "add a context.md, record this plan into it, how you execute it and the results"

#### Agent Actions
- Created `context.md` to persist the full design history, architectural plan, prompt log, execution tracker, and test verification results across sessions.

---

## 3. Implementation Plan & Component Structure

```
ImpleGym/
|-- .github/workflows/ci.yml       # Automated CI pipeline (lint, typecheck, test, e2e, docker)
|-- docker-compose.yml             # Local dev stack: PostgreSQL 16 + FastAPI
|-- Dockerfile                     # Multi-stage container (GCC, Clang, Python, Fast API)
|-- Makefile                       # Developer commands (dev, test, lint, format, docker-up)
|-- pyproject.toml                 # Dependencies, tool configurations (Ruff, Mypy, Pytest)
|-- context.md                     # Persistent AI memory & execution journal
|-- implegym/
|   |-- __init__.py
|   |-- config.py                  # Pydantic Settings (.env, database, OpenAI key)
|   |-- db/
|   |   |-- __init__.py
|   |   |-- database.py            # Async SQLAlchemy engine & async session pool
|   |   +-- models.py              # PostgreSQL ORM models (Problem, Session, Submission, etc.)
|   |-- problems/
|   |   |-- __init__.py
|   |   |-- indexer.py             # Yosupo repo parser, TOML/markdown extractor
|   |   +-- catalog.py             # Problem query service (search, filter, pagination)
|   |-- sampler/
|   |   |-- __init__.py
|   |   +-- distribution.py        # Bounded Gaussian & Skew-Normal sampler
|   |-- judge/
|   |   |-- __init__.py
|   |   |-- compiler.py            # Multi-compiler runner (GCC 17/20/23, Clang, flags)
|   |   +-- runner.py              # Testcase execution, testlib checker, TLE/MLE/RE/AC
|   |-- session/
|   |   |-- __init__.py
|   |   +-- tracker.py             # Stopwatch state machine & session lifecycle
|   |-- ai/
|   |   |-- __init__.py
|   |   |-- client.py              # OpenAI API client wrapper with structured schemas
|   |   |-- refiner.py             # Per-submission CP code reviewer
|   |   +-- generator.py           # Composite problem synthesizer & auto-validator
|   |-- server/
|   |   |-- __init__.py
|   |   +-- app.py                 # FastAPI REST + WebSocket API endpoints
|   +-- static/                    # Modern interactive web UI (KaTeX, Monaco, Stopwatch)
+-- tests/
    |-- conftest.py                # Testcontainers PostgreSQL fixtures & mocks
    |-- test_sampler_property.py   # Hypothesis property-based tests
    |-- test_compiler_matrix.py    # Multi-compiler standard tests
    |-- test_judge_differential.py # Judge & differential stress tests
    |-- test_session_lifecycle.py  # Stopwatch & session persistence tests
    |-- test_ai.py                 # AI refiner & problem generator tests
    |-- benchmark/
    |   +-- test_benchmarks.py     # Pytest-Benchmark performance tests
    +-- e2e/
        +-- test_ui_playwright.py  # Playwright headless browser E2E tests
```

---

## 4. Execution Tracker & Results

| Step | Component | Status | Verification & Notes |
| :--- | :--- | :--- | :--- |
| 1 | `pyproject.toml`, `config.py`, `.env.example` | Planned | Modern packaging & dependency definitions |
| 2 | PostgreSQL Database Schema & ORM (`db/`) | Planned | Models: Problem, PracticeSession, Submission, AIReview, CustomProblem |
| 3 | Problem Indexer & Catalog (`problems/`) | Planned | Yosupo parser, category mapper, 1-10 difficulty rating index |
| 4 | Gaussian & Skew-Normal Sampler (`sampler/`) | Planned | Bounded $\mathcal{N}(\mu, \sigma^2)$ and Azzalini skew-normal sampling |
| 5 | Multi-Compiler Judge & Runner (`judge/`) | Planned | C++17/20/23, Clang, Python, testlib checker runner, TLE/MLE/RE |
| 6 | Session Tracker & Stopwatch Engine (`session/`) | Planned | Stopwatch lifecycle (starts on problem open, stops on AC) |
| 7 | AI Refiner & Problem Generator (`ai/`) | Planned | OpenAI GPT-4o CP code refinement & composite problem generator |
| 8 | FastAPI Server & Interactive Web UI (`server/`, `static/`) | Planned | REST API, WebSockets, KaTeX math, Monaco editor, Live timer HUD |
| 9 | Automated Test Suites (`tests/`) | Planned | Playwright E2E, Hypothesis property tests, Testcontainers, Benchmarks |
| 10 | DevOps Tooling (`Dockerfile`, `docker-compose.yml`, CI) | Planned | Multi-stage Docker, GitHub Actions, Makefile |

*(This section will be continuously updated as implementation progresses).*
