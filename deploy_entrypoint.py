"""Initialise an isolated Ithaka database, then launch the API."""
from pathlib import Path
from sqlalchemy import text
from database import Base, engine
import models  # noqa: F401 -- registers metadata

Base.metadata.create_all(bind=engine)
with engine.begin() as connection:
    cursor = connection.connection.driver_connection.cursor()
    # Base.metadata creates the current application schema, including the
    # earlier 001-004 changes. Only the additive canonical/provenance/search
    # migrations need to run here; replaying 001-004 creates duplicate indexes
    # on a fresh database.
    for migration in sorted(Path("migrations").glob("00[5-7]_*.sql")):
        cursor.execute(migration.read_text())
print("Ithaka database ready")
