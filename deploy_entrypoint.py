"""Initialise an isolated Ithaka database, then launch the API."""
from pathlib import Path
from sqlalchemy import text
from database import Base, engine
import models  # noqa: F401 -- registers metadata

Base.metadata.create_all(bind=engine)
with engine.begin() as connection:
    cursor = connection.connection.driver_connection.cursor()
    for migration in sorted(Path("migrations").glob("*.sql")):
        cursor.execute(migration.read_text())
print("Ithaka database ready")
