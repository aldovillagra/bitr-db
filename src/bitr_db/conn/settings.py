from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, SecretStr


class DatabaseSettings(BaseModel):
    """
    Configuración común de cualquier base de datos soportada.
    """

    host: str = "localhost"
    port: int = Field(default=5432, ge=1, le=65535)

    database: str
    user: str
    password: SecretStr

    pool_size: int = Field(default=5, ge=1, le=100)
    max_overflow: int = Field(default=10, ge=0, le=500)
    pool_timeout: int = Field(default=30, ge=1, le=3600)
    pool_recycle: int = Field(default=1800, ge=-1)

    pool_pre_ping: bool = True
    pool_use_lifo: bool = True

    echo: bool = False
    application_name: str = "bitr-db"

    @property
    def sqlalchemy_url(self) -> str:
        """
        Debe ser implementado por cada backend.
        """
        raise NotImplementedError

    @property
    def connect_args(self) -> dict[str, Any]:
        """
        Argumentos específicos del driver.
        """
        return {}

    @property
    def engine_kwargs(self) -> dict[str, Any]:
        return {
            "pool_size": self.pool_size,
            "max_overflow": self.max_overflow,
            "pool_timeout": self.pool_timeout,
            "pool_recycle": self.pool_recycle,
            "pool_pre_ping": self.pool_pre_ping,
            "pool_use_lifo": self.pool_use_lifo,
            "echo": self.echo,
            "future": True,
            "connect_args": self.connect_args,
        }
