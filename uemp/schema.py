"""
schema.py — Keeps an existing database in step with the models.

THE PROBLEM
    `db.create_all()` creates MISSING TABLES, but it never changes a table
    that already exists. When a new feature adds a column (for example
    "is_completed" on semesters), a live database created earlier would not
    have it, and every page using that table would crash.

WHAT THIS FILE DOES
    `upgrade_schema()` compares every table in the models with the real
    database and adds any column that is missing (ALTER TABLE ... ADD COLUMN).
    It only ever ADDS columns, so it can never delete or change existing data.

RULE FOR NEW COLUMNS
    A new column must either allow empty values (nullable) or have a
    server_default (e.g. server_default=false()), so existing rows get a value.
    Otherwise startup stops with a clear message instead of guessing.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.schema import MetaData


def _default_sql(column, dialect) -> str:
    """The DEFAULT clause for a column, written for this database (e.g. 'false' or '0')."""
    if column.server_default is None:
        return ""
    value = column.server_default.arg
    compiled = value if isinstance(value, str) else value.compile(dialect=dialect, compile_kwargs={"literal_binds": True})
    return f" DEFAULT {compiled}"


def missing_columns(engine: Engine, metadata: MetaData) -> list[tuple[str, str]]:
    """(table, column) pairs defined in the models but absent from the database."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    missing = []
    for table in metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all() makes whole tables
        have = {c["name"] for c in inspector.get_columns(table.name)}
        missing += [(table.name, c.name) for c in table.columns if c.name not in have]
    return missing


def upgrade_schema(engine: Engine, metadata: MetaData) -> list[str]:
    """Add every missing column. Returns a list like ['semesters.is_completed'] for the log."""
    added = []
    preparer = engine.dialect.identifier_preparer
    with engine.begin() as conn:
        for table_name, column_name in missing_columns(engine, metadata):
            column = metadata.tables[table_name].c[column_name]
            if not column.nullable and column.server_default is None:
                raise RuntimeError(
                    f"Cannot add {table_name}.{column_name} automatically: give it a server_default "
                    "or make it nullable."
                )
            column_type = column.type.compile(dialect=engine.dialect)
            not_null = "" if column.nullable else " NOT NULL"
            conn.execute(text(
                f"ALTER TABLE {preparer.quote(table_name)} ADD COLUMN {preparer.quote(column_name)} "
                f"{column_type}{_default_sql(column, engine.dialect)}{not_null}"
            ))
            added.append(f"{table_name}.{column_name}")
    return added
