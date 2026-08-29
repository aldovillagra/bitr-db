from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr
from sqlalchemy import URL

from bitr_db.conn.settings import DatabaseSettings


class MySQLSettings(DatabaseSettings):
    """
    Configuración específica de MySQL.
    """

    port: int = Field(default=3306, ge=1, le=65535)
    password: SecretStr = SecretStr("mysql")
    driver: Literal["pymysql"] = "pymysql"
    charset: str = "utf8mb4"
    connect_timeout: int = Field(default=10, ge=1, le=300)

    @property
    def sqlalchemy_url(self) -> str | URL:
        return URL.create(
            drivername=f"mysql+{self.driver}",
            username=self.user,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=self.database,
            query={
                "charset": self.charset,
            },
        )

    @property
    def connect_args(self) -> dict[str, int]:
        return {
            "connect_timeout": self.connect_timeout,
        }


Settings = MySQLSettings
