from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateColumn

from src.models import Base, EventType
from src.setup import settings


engine = create_engine(url=settings.db)
SessionLocal = sessionmaker(bind=engine)

Base.metadata.create_all(engine)


def add_missing_columns() -> None:
    """create_all() skips existing tables, so add any model columns they're missing.

    Only adds columns (never alters or drops). A new NOT NULL column needs a
    server_default so existing rows get a value.
    """
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in existing:
                    ddl = CreateColumn(column).compile(dialect=engine.dialect)
                    conn.exec_driver_sql(f"ALTER TABLE {table.name} ADD COLUMN {ddl}")


add_missing_columns()


EVENT_TYPES = [
    "Breakout",
    "Encounter",
    "Main Session",
    "SMC Store",
    "Check In",
    "Night Life",
    "Check Wristbands",
    "Kaleo Interest Form",
    "Basketball Tournament",
]


def seed_event_types() -> None:
    """Insert any EVENT_TYPES not already in the table; safe to run on every startup."""
    with SessionLocal() as session:
        existing = set(session.scalars(select(EventType.name)))
        session.add_all(EventType(name=name) for name in EVENT_TYPES if name not in existing)
        session.commit()


seed_event_types()
