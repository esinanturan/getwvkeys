"""many devices to many users

Revision ID: 684292138a0a
Revises: c8ce82d0c054
Create Date: 2024-07-23 19:26:35.940451

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "684292138a0a"
down_revision: Union[str, None] = "c8ce82d0c054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = "c8ce82d0c054"


def upgrade() -> None:
    # rename code to info
    op.alter_column("devices", "code", new_column_name="info", existing_type=sa.String(255))
    # add new code column with a more unique value
    op.add_column(
        "devices",
        sa.Column(
            "code",
            sa.String(length=255),
            nullable=False,
            default=sa.text(
                """
                SHA2(
                    CONCAT(
                        SHA2(CONVERT(client_id_blob_filename USING utf8mb4), 256),
                        ':',
                        SHA2(CONVERT(client_id_blob_filename USING utf8mb4), 256)
                    ),
                    256
                )
                """
            ),
        ),
    )

    # remove all rows where uploaded_by is null, as they are not associated with a user
    op.execute("DELETE FROM devices WHERE uploaded_by IS NULL")

    # set uploaded_by to non nullable
    op.alter_column("devices", "uploaded_by", nullable=False, existing_type=sa.String(255))

    # generate code for rows as a sha256 in the format of "client_id_blob_filename sha256:device_private_key sha265:uploaded_by"
    op.execute(
        """
        UPDATE devices
        SET code = SHA2(
            CONCAT(
                SHA2(CONVERT(client_id_blob_filename USING utf8mb4), 256),
                ':',
                SHA2(CONVERT(client_id_blob_filename USING utf8mb4), 256)
            ),
            256
        )
        """
    )

    # for mapping, cause we need to dedupe and create a unique constraint
    old_devices = op.get_bind().execute(sa.text("SELECT * FROM devices")).fetchall()

    user_device_insert = """INSERT INTO user_device (user_id, device_code) VALUES """
    for device in old_devices:
        user_device_insert += f"('{device[6]}', '{device[7]}'),"

    # remove trailing comma
    user_device_insert = user_device_insert[:-1]

    # deduplicate devices by code
    op.execute("DELETE FROM devices WHERE id NOT IN (SELECT MIN(id) FROM devices GROUP BY code)")

    # add a unique constraint to the code column
    op.create_unique_constraint(None, "devices", ["code"])

    # reset ids
    # op.execute("SET @id=0; UPDATE devices SET id=@id:=@id+1")

    # ### commands auto generated by Alembic - please adjust! ###
    # create a user <-> device association table
    op.create_table(
        "user_device",
        sa.Column("user_id", sa.VARCHAR(255), nullable=False),
        sa.Column("device_code", sa.VARCHAR(255), nullable=False),
        sa.ForeignKeyConstraint(["device_code"], ["devices.code"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    # remove useless columns, these never served any purpose
    op.drop_column("devices", "security_level")
    op.drop_column("devices", "session_id_type")
    # ### end Alembic commands ###

    # insert data into user_device
    op.execute(user_device_insert)


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for this migration.")
