"""Command-line interface for ImpleGym."""

import asyncio
from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from implegym.config import settings
from implegym.db.database import get_engine, init_db, session_scope
from implegym.problems.catalog import ProblemCatalogService
from implegym.problems.indexer import ProblemIndexer

app = typer.Typer(
    name="implegym",
    help="ImpleGym - Competitive Programming Implementation Training Gym",
)
console = Console()


@app.command()
def serve(
    host: str = typer.Option(settings.host, "--host", "-h", help="Host binding"),
    port: int = typer.Option(settings.port, "--port", "-p", help="Port number"),
    reload: bool = typer.Option(settings.debug, "--reload", "-r", help="Enable auto-reload"),
) -> None:
    """Launch ImpleGym API and Web UI server."""
    console.print(
        f"[bold green]Starting ImpleGym Server on[/bold green] [bold cyan]http://{host}:{port}[/bold cyan]"
    )
    uvicorn.run("implegym.server.app:app", host=host, port=port, reload=reload)


@app.command()
def seed() -> None:
    """Seed initial library-checker problems into PostgreSQL database."""

    async def _seed() -> None:
        await init_db()
        async with session_scope() as session:
            indexer = ProblemIndexer(session)
            count = await indexer.seed_default_problems()
            console.print(
                f"[bold green]Successfully seeded {count} problems into database.[/bold green]"
            )

    asyncio.run(_seed())


@app.command()
def scan(
    repo_path: Path = typer.Argument(
        ..., help="Path to local yosupo06/library-checker-problems clone"
    ),
) -> None:
    """Scan and index a local library-checker-problems repository clone."""

    async def _scan() -> None:
        await init_db()
        async with session_scope() as session:
            indexer = ProblemIndexer(session)
            count = await indexer.scan_local_yosupo_repo(repo_path)
            console.print(
                f"[bold green]Scanned repository and indexed {count} new problems.[/bold green]"
            )

    asyncio.run(_scan())


@app.command()
def sync_yosupo(
    repo_dir: Path | None = typer.Option(
        None, "--repo-dir", "-d", help="Custom local repo path to clone or sync into"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force re-generation and compilation of test cases for all problems",
    ),
    max_tests: int | None = typer.Option(
        None,
        "--max-tests",
        "-n",
        help="Optional cap on generated test cases per problem (defaults to full count in info.toml)",
    ),
) -> None:
    """Clone or pull official yosupo06/library-checker-problems and sync all problems to PostgreSQL."""
    from typing import Any

    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )

    async def _sync() -> None:
        await init_db()
        async with session_scope() as session:
            from implegym.problems.yosupo_syncer import YosupoSyncer

            syncer = YosupoSyncer(session, repo_dir=repo_dir)

            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(bar_width=30),
                TaskProgressColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task_id = progress.add_task("[cyan]Initializing...", total=100)

                def _on_progress(state: dict[str, Any]) -> None:
                    stage = state.get("stage", "")
                    total = state.get("total", 0)
                    current = state.get("current", 0)
                    slug = state.get("current_slug", "")

                    if stage == "git_clone_pull":
                        progress.update(
                            task_id,
                            description="[cyan]Updating Git repo...",
                            total=100,
                            completed=10,
                        )
                    elif stage == "scanning":
                        progress.update(
                            task_id,
                            description="[cyan]Scanning problem files...",
                            total=100,
                            completed=25,
                        )
                    elif stage == "syncing_problems":
                        desc = (
                            f"[bold cyan]Syncing:[/] [green]{slug}[/]"
                            if slug
                            else "[cyan]Syncing problems..."
                        )
                        progress.update(
                            task_id, description=desc, total=total or 100, completed=current
                        )
                    elif stage == "completed":
                        progress.update(
                            task_id,
                            description="[bold green]Sync completed![/]",
                            total=total or current or 100,
                            completed=total or current or 100,
                        )

                count = await syncer.sync_all_problems(
                    progress_callback=_on_progress,
                    force_regenerate_tests=force,
                    max_tests=max_tests,
                )

            console.print(
                f"[bold green]✨ Successfully synchronized {count} Yosupo problems into database![/bold green]"
            )

    asyncio.run(_sync())


@app.command("set-difficulty")
def set_difficulty(
    slug: str = typer.Argument(..., help="Problem slug identifier, e.g. aplusb"),
    difficulty: int = typer.Argument(..., help="New difficulty rating between 1 and 10"),
) -> None:
    """Manually update difficulty rating for a problem."""

    async def _run() -> None:
        await init_db()
        async with session_scope() as session:
            catalog = ProblemCatalogService(session)
            try:
                updated = await catalog.update_problem(slug, {"difficulty": difficulty})
                typer.echo(
                    f"✅ Successfully updated '{updated.slug}' difficulty to {updated.difficulty}/10"
                )
            except Exception as ex:
                typer.echo(f"❌ Failed to update problem difficulty: {ex}")

    asyncio.run(_run())


@app.command("sync-db")
def sync_db(
    source: str = typer.Option(
        "sqlite+aiosqlite:///data/implegym.db",
        "--source",
        "-s",
        help="Source database URL (e.g. SQLite path)",
    ),
    target: str = typer.Option(
        None,
        "--target",
        "-t",
        help="Target database URL (defaults to DATABASE_URL in config/env)",
    ),
) -> None:
    """Synchronize all problems, sessions, submissions, and AI reviews between two databases."""
    from implegym.db.syncer import DatabaseSyncService

    target_url = target or settings.database_url

    async def _run() -> None:
        typer.echo("🔄 Starting database synchronization...")
        typer.echo(f"   Source: {source}")
        typer.echo(f"   Target: {target_url}")
        syncer = DatabaseSyncService(source_url=source, target_url=target_url)
        try:
            results = await syncer.sync_data()
            typer.echo("✅ Database synchronization complete:")
            for k, v in results.items():
                typer.echo(f"   - {k}: {v}")
        except Exception as ex:
            if "5432" in str(ex) or "connect" in str(ex).lower():
                typer.echo(
                    "❌ Synchronization failed: Target PostgreSQL server is not running on port 5432."
                )
                typer.echo(
                    "   Tip: Start PostgreSQL via Docker with 'docker-compose up -d postgres' or check your DATABASE_URL."
                )
            else:
                typer.echo(f"❌ Synchronization failed: {ex}")

    asyncio.run(_run())


@app.command()
def list_probs() -> None:
    """List indexed problems in terminal."""

    async def _list() -> None:
        await init_db()
        async with session_scope() as session:
            catalog = ProblemCatalogService(session)
            from implegym.models.schemas import ProblemFilterParams

            problems, total = await catalog.list_problems(ProblemFilterParams(page_size=100))

            table = Table(title=f"Indexed Problems ({total} total)")
            table.add_column("Slug", style="cyan")
            table.add_column("Title", style="bold")
            table.add_column("Category", style="magenta")
            table.add_column("Difficulty", style="yellow")
            table.add_column("Solved", style="green")

            for p in problems:
                table.add_row(
                    p.slug,
                    p.title,
                    p.category,
                    f"{p.difficulty}/10",
                    "✓ AC" if p.is_solved else "-",
                )
            console.print(table)

    asyncio.run(_list())


@app.command("reset")
@app.command("db-reset")
def reset_system(
    testcases: bool = typer.Option(
        False, "--testcases", "-t", help="Clear only on-disk generated testcases in data/testcases/"
    ),
    history: bool = typer.Option(
        False, "--history", help="Clear only practice sessions and submission history"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Reset database records and/or cached on-disk testcases."""
    import shutil

    from sqlalchemy import text

    if not yes:
        target_desc = (
            "generated testcases"
            if testcases
            else ("submission history" if history else "entire database & testcase cache")
        )
        confirm = typer.confirm(f"⚠️ Are you sure you want to reset {target_desc}?", default=False)
        if not confirm:
            console.print("[yellow]Reset cancelled.[/yellow]")
            return

    async def _do_reset() -> None:
        await init_db()
        async with session_scope() as session:
            if history:
                await session.execute(text("DELETE FROM ai_reviews"))
                await session.execute(text("DELETE FROM submissions"))
                await session.execute(text("DELETE FROM practice_sessions"))
                await session.commit()
                console.print(
                    "[bold green]✅ Successfully cleared practice sessions and submission history.[/bold green]"
                )
            elif testcases:
                tc_path = Path("data") / "testcases"
                if tc_path.exists():
                    shutil.rmtree(tc_path)
                    tc_path.mkdir(parents=True, exist_ok=True)
                console.print(
                    "[bold green]✅ Successfully cleared on-disk generated testcases (data/testcases/).[/bold green]"
                )
            else:
                # Full reset
                await session.execute(text("DELETE FROM ai_reviews"))
                await session.execute(text("DELETE FROM submissions"))
                await session.execute(text("DELETE FROM practice_sessions"))
                await session.execute(text("DELETE FROM problems"))
                await session.commit()

                tc_path = Path("data") / "testcases"
                if tc_path.exists():
                    shutil.rmtree(tc_path)
                    tc_path.mkdir(parents=True, exist_ok=True)

                console.print(
                    "[bold green]✅ Successfully reset database and testcase files.[/bold green]"
                )
                console.print(
                    "[dim]Tip: Run 'implegym sync-yosupo' to re-sync all problems fresh from repository.[/dim]"
                )

    asyncio.run(_do_reset())


@app.command("db-inspect")
def db_inspect() -> None:
    """Inspect active database (SQLite or PostgreSQL), table schemas, row counts, and health."""
    from sqlalchemy import func, select

    from implegym.db.models import AIReview, CustomProblem, PracticeSession, Problem, Submission

    async def _inspect() -> None:
        await init_db()
        eng = get_engine()
        actual_url = str(eng.url)
        engine_type = "SQLite" if "sqlite" in actual_url else "PostgreSQL"

        console.print("\n[bold cyan]🔍 ImpleGym Database Inspector[/bold cyan]")
        console.print(f"[bold]Active Engine:[/] [green]{engine_type}[/green]")
        console.print(f"[bold]Connection URL:[/] [dim]{actual_url}[/dim]\n")

        async with session_scope() as session:
            # 1. Row counts overview table
            table = Table(
                title="📊 Database Tables Overview", show_header=True, header_style="bold magenta"
            )
            table.add_column("Table Name", style="cyan")
            table.add_column("Description", style="white")
            table.add_column("Row Count", justify="right", style="green")

            models_meta = [
                ("problems", Problem, "Library Checker problem catalog & testcases"),
                ("custom_problems", CustomProblem, "AI-generated composite problems"),
                ("practice_sessions", PracticeSession, "Practice & contest workout sessions"),
                ("submissions", Submission, "User code submissions & judge verdicts"),
                ("ai_reviews", AIReview, "AI code refinements and feedbacks"),
            ]

            for name, model_cls, desc in models_meta:
                try:
                    count_stmt = select(func.count()).select_from(model_cls)
                    count_res = await session.execute(count_stmt)
                    count_val = count_res.scalar() or 0
                    table.add_row(name, desc, str(count_val))
                except Exception as ex:
                    table.add_row(name, desc, f"[red]Error: {ex}[/red]")

            console.print(table)

            # 2. Detailed Problem Category Distribution
            try:
                cat_stmt = (
                    select(Problem.category, func.count(Problem.id))
                    .group_by(Problem.category)
                    .order_by(func.count(Problem.id).desc())
                )
                cat_res = await session.execute(cat_stmt)
                cats = cat_res.all()

                if cats:
                    cat_table = Table(
                        title="\n📚 Problem Categories Breakdown",
                        show_header=True,
                        header_style="bold blue",
                    )
                    cat_table.add_column("Category", style="magenta")
                    cat_table.add_column("Count", justify="right", style="green")
                    for c_name, c_cnt in cats[:15]:
                        cat_table.add_row(c_name or "General", str(c_cnt))
                    console.print(cat_table)
            except Exception:
                pass

    asyncio.run(_inspect())


@app.command("db-schema")
def db_schema(
    table_name: str | None = typer.Argument(
        None,
        help="Table name to inspect schema (e.g. problems, submissions). Leave empty for all tables.",
    ),
) -> None:
    """Inspect column definitions, types, nullability, and keys for database tables."""
    from implegym.db.models import Base

    async def _schema() -> None:
        await init_db()
        tables_to_show = (
            [table_name.lower()]
            if table_name and table_name.lower() in Base.metadata.tables
            else list(Base.metadata.tables.keys())
        )

        if table_name and table_name.lower() not in Base.metadata.tables:
            console.print(
                f"[bold red]Table '{table_name}' not found. Available tables: {', '.join(Base.metadata.tables.keys())}[/bold red]"
            )
            return

        for t_name in tables_to_show:
            t_obj = Base.metadata.tables[t_name]
            schema_table = Table(
                title=f"📋 Schema for table: [bold cyan]{t_name}[/bold cyan]",
                show_header=True,
                header_style="bold magenta",
            )
            schema_table.add_column("Column Name", style="cyan", no_wrap=True)
            schema_table.add_column("Data Type", style="yellow")
            schema_table.add_column("Nullable", style="white")
            schema_table.add_column("Key / Index", style="green")
            schema_table.add_column("Default", style="dim")

            for col in t_obj.columns:
                key_type = (
                    "🔑 Primary Key"
                    if col.primary_key
                    else ("🔗 Foreign Key" if col.foreign_keys else "")
                )
                schema_table.add_row(
                    col.name,
                    str(col.type),
                    "✓ Yes" if col.nullable else "✗ No",
                    key_type,
                    str(col.default.arg) if col.default is not None else "-",
                )
            console.print(schema_table)
            console.print()

    asyncio.run(_schema())


@app.command("db-view")
def db_view(
    table_name: str = typer.Argument(
        "problems",
        help="Table name to view rows (problems, practice_sessions, submissions, custom_problems, ai_reviews)",
    ),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of rows to display"),
    offset: int = typer.Option(0, "--offset", "-o", help="Offset / starting row index"),
    columns: str | None = typer.Option(
        None,
        "--columns",
        "-c",
        help="Comma-separated column names to show (e.g. id,slug,category,difficulty)",
    ),
) -> None:
    """Browse and inspect actual rows and column values of a database table."""
    from sqlalchemy import text

    from implegym.db.models import Base

    async def _view() -> None:
        await init_db()
        t_name = table_name.lower()
        if t_name not in Base.metadata.tables:
            console.print(
                f"[bold red]Table '{table_name}' not found. Available tables: {', '.join(Base.metadata.tables.keys())}[/bold red]"
            )
            return

        async with session_scope() as session:
            # Query row count
            count_res = await session.execute(text(f"SELECT COUNT(*) FROM {t_name}"))
            total_rows = count_res.scalar() or 0

            # Query rows
            col_clause = "*"
            if columns:
                col_clause = ", ".join([c.strip() for c in columns.split(",") if c.strip()])

            query_str = f"SELECT {col_clause} FROM {t_name} LIMIT {limit} OFFSET {offset}"
            res = await session.execute(text(query_str))
            keys = list(res.keys())
            rows = res.fetchall()

            table = Table(
                title=f"🔎 Viewing [bold cyan]{t_name}[/bold cyan] (Rows {offset + 1}-{min(offset + len(rows), total_rows)} of {total_rows} total)",
                show_header=True,
                header_style="bold blue",
            )
            for k in keys:
                table.add_column(str(k), overflow="ellipsis", max_width=40)

            for row in rows:
                formatted_cells = []
                for val in row:
                    if val is None:
                        formatted_cells.append("[dim]NULL[/dim]")
                    elif isinstance(val, (dict, list)):
                        import json

                        raw_json = json.dumps(val)
                        if len(raw_json) > 40:
                            formatted_cells.append(f"[dim]{raw_json[:35]}...[/dim]")
                        else:
                            formatted_cells.append(raw_json)
                    else:
                        s_val = str(val).replace("\n", " ")
                        if len(s_val) > 40:
                            formatted_cells.append(f"{s_val[:37]}...")
                        else:
                            formatted_cells.append(s_val)
                table.add_row(*formatted_cells)

            console.print(table)
            if offset + len(rows) < total_rows:
                console.print(
                    f"[dim]Tip: Use `--offset {offset + limit}` to view the next page of rows.[/dim]"
                )

    asyncio.run(_view())


@app.command("db-query")
def db_query(
    sql: str = typer.Argument(..., help="SQL query to execute against active database"),
) -> None:
    """Execute a raw SQL query against the active database and print formatted table."""
    from sqlalchemy import text

    async def _query() -> None:
        await init_db()
        async with session_scope() as session:
            try:
                res = await session.execute(text(sql))
                if res.returns_rows:
                    keys = list(res.keys())
                    rows = res.fetchall()

                    table = Table(
                        title=f"SQL Query Result ({len(rows)} rows)",
                        show_header=True,
                        header_style="bold cyan",
                    )
                    for k in keys:
                        table.add_column(str(k))

                    for row in rows[:50]:
                        table.add_row(
                            *[
                                str(val)[:80] if val is not None else "[dim]NULL[/dim]"
                                for val in row
                            ]
                        )

                    console.print(table)
                    if len(rows) > 50:
                        console.print(f"[dim]... truncated ({len(rows) - 50} more rows)[/dim]")
                else:
                    await session.commit()
                    console.print(
                        f"[bold green]Query executed successfully (Rows affected: {res.rowcount}).[/bold green]"
                    )
            except Exception as ex:
                console.print(f"[bold red]SQL Execution Error:[/] {ex}")

    asyncio.run(_query())


@app.command("db-record")
def db_record(
    table_name: str = typer.Argument(
        ...,
        help="Table name (problems, submissions, practice_sessions, custom_problems, ai_reviews)",
    ),
    ident: str = typer.Argument(
        ..., help="Record ID (integer) or Problem Slug (e.g. 1 or 'aplusb')"
    ),
) -> None:
    """Inspect a single database record in full detail with formatted fields."""
    import json

    from rich.panel import Panel
    from sqlalchemy import text

    from implegym.db.models import Base

    async def _record() -> None:
        await init_db()
        t_name = table_name.lower()
        if t_name not in Base.metadata.tables:
            console.print(
                f"[bold red]Table '{table_name}' not found. Available tables: {', '.join(Base.metadata.tables.keys())}[/bold red]"
            )
            return

        async with session_scope() as session:
            has_slug = "slug" in [c.name for c in Base.metadata.tables[t_name].columns]
            if ident.isdigit():
                q = f"SELECT * FROM {t_name} WHERE id = :ident"
                params = {"ident": int(ident)}
            elif has_slug:
                q = f"SELECT * FROM {t_name} WHERE slug = :ident"
                params = {"ident": ident}
            else:
                q = f"SELECT * FROM {t_name} WHERE id = :ident"
                params = {"ident": ident}

            res = await session.execute(text(q), params)
            row = res.mappings().first()
            if not row:
                console.print(
                    f"[bold red]Record '{ident}' not found in table '{t_name}'.[/bold red]"
                )
                return

            console.print(
                Panel(
                    f"[bold green]🔍 Detailed Record View[/bold green] | Table: [cyan]{t_name}[/] | Identifier: [yellow]{ident}[/]",
                    expand=False,
                )
            )

            rec_table = Table(show_header=True, header_style="bold magenta")
            rec_table.add_column("Column / Field", style="bold cyan", no_wrap=True, width=22)
            rec_table.add_column("Type", style="dim", width=12)
            rec_table.add_column("Value", style="white")

            for k, val in row.items():
                val_type = type(val).__name__
                if val is None:
                    rec_table.add_row(k, "null", "[dim]NULL[/dim]")
                elif isinstance(val, (dict, list)):
                    pretty_j = json.dumps(val, indent=2, ensure_ascii=False)
                    rec_table.add_row(k, "json", pretty_j)
                elif isinstance(val, str) and (val.startswith("{") or val.startswith("[")):
                    try:
                        parsed = json.loads(val)
                        pretty_j = json.dumps(parsed, indent=2, ensure_ascii=False)
                        rec_table.add_row(k, "json", pretty_j)
                    except Exception:
                        rec_table.add_row(k, val_type, val)
                elif isinstance(val, str) and "\n" in val:
                    rec_table.add_row(k, val_type, val)
                else:
                    rec_table.add_row(k, val_type, str(val))

            console.print(rec_table)

    asyncio.run(_record())


if __name__ == "__main__":
    app()
