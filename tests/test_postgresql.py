from __future__ import annotations

from sqlalchemy import URL
from sqlalchemy.engine import make_url

from bitr_db.conn import (
    DatabaseConnection,
    MariaDBSettings,
    MySQLSettings,
    PostgresSettings,
)


def test_postgres_uses_psycopg_driver():
    settings = PostgresSettings(
        database="test",
        user="test",
        password="secret",
    )

    url = make_url(str(settings.sqlalchemy_url))

    assert url.drivername == "postgresql+psycopg"
    assert url.host == "localhost"
    assert url.port == 5432
    assert url.database == "test"


def test_postgres_identifier_uses_double_quotes():
    settings = PostgresSettings(
        database="test",
        user="test",
        password="secret",
    )

    db = DatabaseConnection(settings)
    assert db._quote_identifier("customer") == "customer"

    db.close()


def test_postgres_schema_identifier_is_quoted():
    settings = PostgresSettings(
        database="test",
        user="test",
        password="secret",
    )

    db = DatabaseConnection(settings)

    assert db._quote_identifier("public.customer") == ("public.customer")

    db.close()
