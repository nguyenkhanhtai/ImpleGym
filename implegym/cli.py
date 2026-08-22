"""Command-line interface for ImpleGym."""

import asyncio
from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from implegym.config import settings
from implegym.db.database import init_db, session_scope
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
) -> None:
    """Clone or pull official yosupo06/library-checker-problems and sync all problems to PostgreSQL."""

    async def _sync() -> None:
        await init_db()
        async with session_scope() as session:
            from implegym.problems.yosupo_syncer import YosupoSyncer

            syncer = YosupoSyncer(session, repo_dir=repo_dir)
            console.print(
                "[bold cyan]Fetching & synchronizing official Yosupo Library Checker problems...[/bold cyan]"
            )
            count = await syncer.sync_all_problems()
            console.print(
                f"[bold green]Successfully synchronized {count} new/updated Yosupo problems into database![/bold green]"
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


if __name__ == "__main__":
    app()
