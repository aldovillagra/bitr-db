from bitr_db.conn.base import DatabaseConnection
from bitr_db.conn.mariadb import MariaDBSettings
from bitr_db.conn.mysql import MySQLSettings
from bitr_db.conn.postgres import PostgresSettings

PostgresConnection = DatabaseConnection
MySQLConnection = DatabaseConnection
MariaDBConnection = DatabaseConnection

PostgresSetting = PostgresSettings

__all__ = [
    "DatabaseConnection",
    "PostgresConnection",
    "MySQLConnection",
    "MariaDBConnection",
    "PostgresSettings",
    "MySQLSettings",
    "MariaDBSettings",
    "PostgresSetting",
]
