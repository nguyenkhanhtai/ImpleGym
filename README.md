# 🏋️‍♂️ ImpleGym

> **Competitive Programming Implementation Training Gym** based on the official [Yosupo Library Checker](https://github.com/yosupo06/library-checker-problems) problem repository.

ImpleGym helps competitive programmers master standard data structures, algorithms, and implementation speed through Gaussian/Skew-Normal sampled problem workouts, real-time stopwatch contests, multi-compiler local judging, and AI-powered code reviews.

---

## 🌟 Key Features

- **⚡ Multi-Page Web UI**:
  - **Workout / Practice Mode**: Real-time stopwatch, target time benchmarks, interactive problem sampler.
  - **Dedicated Contest Mode**: Timed multi-problem contests (1, 2, 3, 5, or 7 problems) with instant switching and AC tracking.
  - **Problem Explorer**: Browse, search, filter by category/tags/difficulty, with live Yosupo sync progress modal.
  - **AI Problem Forge**: Synthesize novel composite competitive programming problems with GPT-4o.
  - **History & Analytics**: Track submission records, AC rates, code diffs, and execution times.
- **🔄 Smart Yosupo Synchronization**:
  - Automatically clones and syncs official Library Checker problems.
  - **Live Progress Tracking**: SSE streaming in Web UI and multi-column interactive progress bar (`rich`) in CLI.
  - **Smart Testcase Caching**: Skips re-compiling existing problem testcases to sync in seconds.
- **⚖️ Local Multi-Compiler Judge**:
  - Supports **C++17, C++20, C++23** (`g++`, `clang++`) with `-O3` optimization flags.
  - Supports **Python 3.11+**.
  - Local process isolation, TLE/MLE detection, and token-based whitespace-normalized output comparison.
- **💾 Dual Database Engine**:
  - **SQLite Fallback**: Zero-configuration, local database (`data/implegym.db`) that works immediately.
  - **PostgreSQL**: Production-grade async database support via `asyncpg`.
- **🔍 Built-in Database Inspection Tools**:
  - Terminal CLI commands: `db-inspect`, `db-schema`, `db-view`, `db-record`, `db-query`.
  - Web GUI support via **Adminer** on port `8080`.

---

## 🚀 Quick Start & Installation

### Prerequisites

- **Python 3.11+**
- **C++ Compilers**: `g++` or `clang++`
- **Package Manager**: [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`
- **Docker & Docker Compose** *(optional, for PostgreSQL + Adminer)*

### 1. Clone & Setup Environment

```bash
# Clone the repository
git clone https://github.com/nguyenkhanhtai/ImpleGym.git
cd ImpleGym

# Install dependencies using uv
uv sync --extra dev
```

### 2. Environment Configuration (Optional)

Copy `.env.example` to `.env` if you want to customize ports, database, or OpenAI API key:

```bash
cp .env.example .env
```

Key environment variables:
- `DATABASE_URL`: `sqlite+aiosqlite:///data/implegym.db` (default) or `postgresql+asyncpg://postgres:postgrespassword@localhost:5432/implegym`
- `OPENAI_API_KEY`: Required for AI Problem Forge and AI Review features.

---

## 💻 Running the Application

### Option A: Local Development (Recommended)

Start the ImpleGym server with local SQLite database:

```bash
# Run server via uv
uv run implegym serve

# Or with custom host/port:
uv run implegym serve --host 0.0.0.0 --port 8000
```

Open your browser and navigate to: **[http://localhost:8000](http://localhost:8000)**

---

### Option B: Running with Docker Compose (PostgreSQL + API + Adminer)

If you prefer running with PostgreSQL and web database GUI:

```bash
# Start all containers in the background
docker-compose up -d
```

- **Web App**: [http://localhost:8000](http://localhost:8000)
- **Database Adminer Web GUI**: [http://localhost:8080](http://localhost:8080)

---

## 🛠️ CLI Commands Reference

ImpleGym provides a rich CLI powered by Typer and Rich:

```bash
# Start the web server and API
uv run implegym serve

# Sync official Library Checker problems (with interactive Rich progress bar)
uv run implegym sync-yosupo

# Force regenerate all test cases from scratch
uv run implegym sync-yosupo --force

# List indexed problems in terminal
uv run implegym list-probs

# Customize difficulty of a problem (1 to 10)
uv run implegym set-difficulty <slug> <difficulty>

# Sync data between two databases (e.g. SQLite to PostgreSQL)
uv run implegym sync-db --source sqlite+aiosqlite:///data/implegym.db --target postgresql+asyncpg://postgres:postgrespassword@localhost:5432/implegym
```

---

## 🔍 Database Inspection CLI Tools

Inspect tables, schemas, rows, and records directly from your terminal:

```bash
# 1. Overview of active database engine, connection status, row counts & categories
uv run implegym db-inspect

# 2. View column definitions, data types, nullability, and primary/foreign keys
uv run implegym db-schema [table_name]

# 3. Browse rows and columns in formatted tables
uv run implegym db-view problems --limit 10
uv run implegym db-view problems --limit 5 --columns id,slug,title,difficulty

# 4. View a single record in full detail (with formatted JSON test cases and markdown)
uv run implegym db-record problems aplusb
uv run implegym db-record submissions 1
uv run implegym db-record practice_sessions 1

# 5. Execute custom raw SQL queries
uv run implegym db-query "SELECT slug, category, difficulty FROM problems WHERE difficulty >= 5 LIMIT 10"
```

---

## 🧪 Testing

Run the comprehensive automated test suite (56+ unit, integration, and benchmark tests):

```bash
# Run unit and integration tests
uv run pytest -v

# Run with test coverage
uv run pytest --cov=implegym

# Run Playwright end-to-end browser tests
uv run pytest -m e2e
```

---

## 📁 Project Structure

```
ImpleGym/
├── implegym/
│   ├── ai/               # OpenAI GPT-4o problem synthesis & code review
│   ├── db/               # SQLAlchemy async models, engine, migration & syncer
│   ├── judge/            # Local compiler runner & output comparator
│   ├── models/           # Pydantic schemas & data transfer models
│   ├── problems/         # Yosupo problem indexer, syncer & progress tracker
│   ├── sampler/          # Gaussian & Skew-Normal problem sampling algorithms
│   ├── server/           # FastAPI backend routes & SSE streaming
│   ├── session/          # Stopwatch & multi-problem contest session engine
│   ├── static/           # Multi-page responsive frontend (HTML, CSS, JS)
│   ├── cli.py            # Typer CLI & Database Inspector
│   └── config.py         # Pydantic application settings & environment
├── tests/                # Pytest suites (unit, property, simulation, e2e)
├── docker-compose.yml    # PostgreSQL + ImpleGym API + Adminer setup
├── Dockerfile            # Multi-stage production container image
├── pyproject.toml        # Project dependencies and configuration
└── README.md             # Project documentation
```

---

## 📜 License

MIT License © 2026 ImpleGym Team
