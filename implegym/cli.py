"""Command-line interface for ImpleGym."""

import asyncio
from pathlib import Path
from typing import Optional
import typer
import uvicorn
from rich.console import Console
from rich.table import Table
from implegym.config import settings
from implegym.db.database import get_db_session, init_db, session_scope
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
    console.print(f"[bold green]Starting ImpleGym Server on[/bold green] [bold cyan]http://{host}:{port}[/bold cyan]")
    uvicorn.run("implegym.server.app:app", host=host, port=port, reload=reload)


@app.command()
def seed() -> None:
    """Seed initial library-checker problems into PostgreSQL database."""
    async def _seed() -> None:
        await init_db()
        async with session_scope() as session:
            indexer = ProblemIndexer(session)
            count = await indexer.seed_default_problems()
            console.print(f"[bold green]Successfully seeded {count} problems into database.[/bold green]")

    asyncio.run(_seed())


@app.command()
def scan(
    repo_path: Path = typer.Argument(..., help="Path to local yosupo06/library-checker-problems clone")
) -> None:
    """Scan and index a local library-checker-problems repository clone."""
    async def _scan() -> None:
        await init_db()
        async with session_scope() as session:
            indexer = ProblemIndexer(session)
            count = await indexer.scan_local_yosupo_repo(repo_path)
            console.print(f"[bold green]Scanned repository and indexed {count} new problems.[/bold green]")

    asyncio.run(_scan())


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
