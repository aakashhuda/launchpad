"""allow multiple profiles per user

A user may hold more than one profile (e.g. member and founder), so the
one-to-one constraint on profiles.user_id is removed. Profile slug stays unique.

Revision ID: b1f7c2d4a9e0
Revises: 8a14589011c8
Create Date: 2026-10-10 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "b1f7c2d4a9e0"
down_revision: Union[str, None] = "8a14589011c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("profiles_user_id_key", "profiles", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("profiles_user_id_key", "profiles", ["user_id"])
