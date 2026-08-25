"""Configuration settings module for ImpleGym."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server Configuration
    host: str = Field(default="127.0.0.1", description="Server host binding")
    port: int = Field(default=8000, description="Server port")
    debug: bool = Field(default=True, description="Debug mode")

    # Database Configuration (PostgreSQL by default, support sqlite for memory testing)
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/implegym",
        description="Async database connection string",
    )

    # AI Configuration
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API Key for code refinement and problem synthesis",
    )
    openai_model: str = Field(
        default="gpt-4o",
        description="OpenAI model identifier",
    )

    # Toolchain Configuration
    default_cpp_compiler: str = Field(default="g++", description="Default C++ compiler executable")
    default_cpp_standard: str = Field(default="c++20", description="Default C++ language standard")
    default_compiler_flags: str = Field(
        default="-O3 -Wall -Wextra",
        description="Default compiler optimization and diagnostic flags",
    )

    # Path Settings
    base_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent,
        description="Base project directory",
    )
    yosupo_problems_dir: Path | None = Field(
        default=None,
        description="Optional local path to yosupo06/library-checker-problems clone",
    )
    data_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent / "data",
        description="Local data and cache directory",
    )
    sandbox_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent / "sandbox",
        description="Sandbox directory for compilation and running code",
    )
    max_tests_per_problem: int = Field(
        default=10,
        description="Maximum number of testcases to generate per problem (default: 10)",
    )


settings = Settings()
