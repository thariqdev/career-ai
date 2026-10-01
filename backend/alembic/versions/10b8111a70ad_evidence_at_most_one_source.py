"""evidence at most one source

Revision ID: 10b8111a70ad
Revises: e034a498adb5
Create Date: 2026-10-01 18:17:07.482400

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '10b8111a70ad'
down_revision: Union[str, None] = 'e034a498adb5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Written by hand: autogenerate doesn't detect check constraints added to an existing
# table. Must match Evidence.__table_args__ exactly.
CONSTRAINT_NAME = "ck_evidence_at_most_one_source"
CONDITION = (
    "(CASE WHEN work_experience_id IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN project_id IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN education_id IS NOT NULL THEN 1 ELSE 0 END) <= 1"
)


def upgrade() -> None:
    op.create_check_constraint(CONSTRAINT_NAME, "evidence", CONDITION)


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "evidence", type_="check")
