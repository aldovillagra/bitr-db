from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr
from sqlalchemy import URL

from bitr_db.conn.settings import DatabaseSettings


class PostgresSettings(DatabaseSettings):
    """
    Configuración específica de PostgreSQL.
    """

    port: int = Field(default=5432, ge=1, le=65535)
    password: SecretStr = SecretStr("postgres")

    sslmode: Literal[
        "disable",
        "allow",
        "prefer",
        "require",
        "verify-ca",
        "verify-full",
    ] = "prefer"

    driver: Literal["psycopg", "psycopg2"] = "psycopg"

    @property
    def sqlalchemy_url(self) -> str | URL:
        return URL.create(
            drivername=f"postgresql+{self.driver}",
            username=self.user,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=self.database,
            query={
                "sslmode": self.sslmode,
            },
        )

    @property
    def connect_args(self) -> dict[str, str]:
        return {
            "application_name": self.application_name,
        }


# Compatibilidad con el nombre actual
Settings = PostgresSettings
