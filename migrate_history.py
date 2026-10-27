
from sqlalchemy import inspect, text
from app import app
from models import db

NEW_COLUMNS = {
    "old_points": "INTEGER",
    "new_points": "INTEGER",
    "actor_discord_id": "VARCHAR(30)",
}

with app.app_context():
    inspector = inspect(db.engine)

    if "ap_change" not in inspector.get_table_names():
        print("APChange table not found. No changes made.")
    else:
        existing = {
            column["name"]
            for column in inspector.get_columns("ap_change")
        }

        with db.engine.begin() as connection:
            for column_name, column_type in NEW_COLUMNS.items():
                if column_name not in existing:
                    connection.execute(text(
                        f"ALTER TABLE ap_change "
                        f"ADD COLUMN {column_name} {column_type}"
                    ))
                    print(f"Added column: {column_name}")
                else:
                    print(f"Already exists: {column_name}")

        print("History migration complete!")
