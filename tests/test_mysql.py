from __future__ import annotations

from sqlalchemy import URL
from sqlalchemy.engine import make_url

from bitr_db.conn import (
    DatabaseConnection,
    MariaDBSettings,
    MySQLSettings,
    PostgresSettings,
)


def test_mysql_uses_pymysql_driver():
    settings = MySQLSettings(
        database="test",
        user="test",
        password="secret",
    )

    url = make_url(str(settings.sqlalchemy_url))

    assert url.drivername == "mysql+pymysql"
    assert url.host == "localhost"
    assert url.port == 3306
    assert url.database == "test"


def test_mysql_identifier_uses_backticks():
    settings = MySQLSettings(
        database="test",
        user="test",
        password="secret",
    )

    db = DatabaseConnection(settings)

    assert db._quote_identifier("customer") == "customer"

    db.close()


def test_mysql_schema_identifier_is_quoted():
    settings = MySQLSettings(
        database="test",
        user="test",
        password="secret",
    )

    db = DatabaseConnection(settings)

    assert db._quote_identifier("app.customer") == ("app.customer")

    db.close()
