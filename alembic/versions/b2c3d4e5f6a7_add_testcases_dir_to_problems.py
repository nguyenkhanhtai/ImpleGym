"""add_testcases_dir_to_problems

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-25 16:55:00.000000

"""

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema with testcases_dir and perform data migration from JSON blobs to disk."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_cols = {c["name"] for c in insp.get_columns("problems")}

    # 1. Add testcases_dir column to problems table if not present
    with op.batch_alter_table("problems", schema=None) as batch_op:
        if "testcases_dir" not in existing_cols:
            batch_op.add_column(
                sa.Column("testcases_dir", sa.String(length=512), nullable=True)
            )

    # 2. Data Migration: Export existing testcases from JSON column to on-disk files
    res = conn.execute(sa.text("SELECT id, slug, sample_cases FROM problems"))
    rows = res.fetchall()

    for row in rows:
        p_id = row[0]
        slug = row[1]
        raw_cases = row[2]

        if not raw_cases:
            continue

        if isinstance(raw_cases, str):
            try:
                cases = json.loads(raw_cases)
            except Exception:
                cases = []
        else:
            cases = raw_cases

        if not isinstance(cases, list) or len(cases) == 0:
            continue

        # Target testcases directory on disk
        target_dir = Path("data") / "testcases" / slug
        target_dir.mkdir(parents=True, exist_ok=True)

        # Write all testcases to disk
        for idx, tc in enumerate(cases):
            tc_name = tc.get("name") or f"test_{idx:02d}"
            # Sanitize name
            tc_clean_name = "".join(c for c in tc_name if c.isalnum() or c in ("_", "-"))
            in_file = target_dir / f"{tc_clean_name}.in"
            out_file = target_dir / f"{tc_clean_name}.out"

            if not in_file.exists():
                in_file.write_text(tc.get("input", ""), encoding="utf-8")
            if not out_file.exists():
                out_file.write_text(tc.get("output", ""), encoding="utf-8")

        # Trim sample_cases in DB to only first 2 sample cases for UI display
        clean_samples = cases[:2]
        clean_samples_json = json.dumps(clean_samples)
        dir_str = str(target_dir).replace("\\", "/")

        conn.execute(
            sa.text(
                "UPDATE problems SET sample_cases = :samples, testcases_dir = :t_dir WHERE id = :p_id"
            ),
            {"samples": clean_samples_json, "t_dir": dir_str, "p_id": p_id},
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("problems", schema=None) as batch_op:
        batch_op.drop_column("testcases_dir")
