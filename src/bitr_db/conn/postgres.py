from __future__ import annotations

import re
from typing import Any, Literal, Mapping, Sequence

import pandas as pd
from pydantic import BaseModel, Field, SecretStr, computed_field
from sqlalchemy import Engine, URL, create_engine, text
from sqlalchemy.engine import Connection as SQLAlchemyConnection
from sqlalchemy.sql.elements import TextClause


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_ALLOWED_OPERATORS = {
    "=",
    "!=",
    "<>",
    ">",
    ">=",
    "<",
    "<=",
    "LIKE",
    "ILIKE",
    "IN",
    "NOT IN",
    "IS",
    "IS NOT",
}


class Settings(BaseModel):
    """
    Configuración de conexión PostgreSQL.

    Para producción se recomienda cargar estos valores desde variables
    de entorno usando pydantic-settings.
    """

    host: str = "localhost"
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = "postgres"
    user: str = "postgres"
    password: SecretStr = SecretStr("postgres")

    # Debe ser None, no una cadena vacía.
    dsn: str | None = None

    # Driver
    driver: Literal["psycopg", "psycopg2"] = "psycopg"

    # Pool
    pool_size: int = Field(default=5, ge=1, le=100)
    max_overflow: int = Field(default=10, ge=0, le=500)
    pool_timeout: int = Field(default=30, ge=1, le=3600)
    pool_recycle: int = Field(default=1800, ge=-1)

    pool_pre_ping: bool = True
    pool_use_lifo: bool = True

    # Conectividad
    connect_timeout: int = Field(default=10, ge=1, le=300)

    sslmode: Literal[
        "disable",
        "allow",
        "prefer",
        "require",
        "verify-ca",
        "verify-full",
    ] = "prefer"

    # Observabilidad
    echo: bool = False
    application_name: str = "bitr-db"

    @computed_field
    @property
    def sqlalchemy_url(self) -> str | URL:
        """
        Devuelve un DSN o un objeto URL de SQLAlchemy.

        Se prefiere devolver URL en vez de renderizar manualmente la
        contraseña dentro de un string.
        """
        if self.dsn:
            return self.dsn

        return URL.create(
            drivername=f"postgresql+{self.driver}",
            username=self.user,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=self.database,
            query={
                "connect_timeout": str(self.connect_timeout),
                "sslmode": self.sslmode,
            },
        )

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
            "connect_args": {
                "application_name": self.application_name,
            },
        }


class Connection:
    """
    Capa de acceso síncrona a PostgreSQL mediante SQLAlchemy.

    La clase administra un Engine compartido y crea conexiones cortas
    por operación usando context managers.
    """

    def __init__(self, config: Settings):
        self.config = config
        self.engine: Engine | None = None

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        """
        Valida y cita identificadores SQL.

        Admite:
            table
            schema.table

        No admite SQL arbitrario.
        """
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("El identificador SQL no puede estar vacío")

        parts = identifier.split(".")

        for part in parts:
            if not _IDENTIFIER_PATTERN.fullmatch(part):
                raise ValueError(
                    f"Identificador SQL inválido: {identifier!r}"
                )

        return ".".join(f'"{part}"' for part in parts)

    @staticmethod
    def _validate_operator(operator: str) -> str:
        if not isinstance(operator, str):
            raise ValueError("El operador SQL debe ser un string")

        normalized = operator.upper().strip()

        if normalized not in _ALLOWED_OPERATORS:
            raise ValueError(f"Operador SQL no permitido: {operator!r}")

        return normalized

    def _create_sql(
        self,
        fields: Sequence[str],
        model: str,
        domains: Sequence[Sequence[Any]] | None = None,
    ) -> tuple[TextClause, dict[str, Any]]:
        """
        Construye una consulta SELECT parametrizada.

        Formato esperado de domains:

            [
                ("active", "=", True),
                ("amount", ">=", 100),
                ("id", "IN", [1, 2, 3]),
            ]
        """
        table_sql = self._quote_identifier(model)

        if not fields:
            select_sql = "*"
            normalized_fields: list[str] = []
        else:
            normalized_fields = [
                self._quote_identifier(field)
                for field in fields
            ]
            select_sql = ", ".join(normalized_fields)

        sql_parts = [
            f"SELECT {select_sql}",
            f"FROM {table_sql}",
        ]

        params: dict[str, Any] = {}
        conditions: list[str] = []

        for index, domain in enumerate(domains or []):
            if len(domain) != 3:
                raise ValueError(
                    "Cada dominio debe tener formato "
                    "(campo, operador, valor)"
                )

            field, operator, value = domain
            field_sql = self._quote_identifier(str(field))
            operator = self._validate_operator(str(operator))

            if value is None:
                if operator == "=":
                    operator = "IS"
                elif operator in {"!=", "<>"}:
                    operator = "IS NOT"
                elif operator not in {"IS", "IS NOT"}:
                    raise ValueError(
                        f"El operador {operator} no admite valor None"
                    )

                conditions.append(f"{field_sql} {operator} NULL")
                continue

            if operator in {"IS", "IS NOT"}:
                raise ValueError(
                    f"El operador {operator} requiere valor None"
                )

            if operator in {"IN", "NOT IN"}:
                if isinstance(value, (str, bytes)) or not isinstance(
                    value,
                    Sequence,
                ):
                    raise ValueError(
                        f"{operator} requiere una secuencia de valores"
                    )

                values = list(value)

                if not values:
                    # Evita generar IN () que no es SQL válido.
                    conditions.append(
                        "FALSE" if operator == "IN" else "TRUE"
                    )
                    continue

                placeholders: list[str] = []

                for value_index, item in enumerate(values):
                    param_name = f"p_{index}_{value_index}"
                    placeholders.append(f":{param_name}")
                    params[param_name] = item

                placeholders_sql = ", ".join(placeholders)
                conditions.append(
                    f"{field_sql} {operator} ({placeholders_sql})"
                )
                continue

            param_name = f"p_{index}"
            conditions.append(
                f"{field_sql} {operator} :{param_name}"
            )
            params[param_name] = value

        if conditions:
            sql_parts.append("WHERE " + " AND ".join(conditions))

        if "id" in fields:
            sql_parts.append('ORDER BY "id" ASC')

        return text("\n".join(sql_parts)), params

    def _connect(self) -> Engine:
        """
        Crea el Engine de forma lazy.

        El Engine es seguro de compartir entre operaciones síncronas.
        """
        if self.engine is None:
            self.engine = create_engine(
                self.config.sqlalchemy_url,
                **self.config.engine_kwargs,
            )

        return self.engine

    def search(
        self,
        fields: Sequence[str],
        model: str,
        domain: Sequence[Sequence[Any]] | None = None,
    ) -> pd.DataFrame:
        sql, params = self._create_sql(
            fields=fields,
            model=model,
            domains=domain,
        )

        return self.read_sql(sql, params)

    def read_sql(
        self,
        sql: TextClause,
        params: Mapping[str, Any] | None = None,
    ) -> pd.DataFrame:
        engine = self._connect()

        with engine.connect() as connection:
            return pd.read_sql(
                sql,
                con=connection,
                params=dict(params or {}),
            )

    def get_conn(self) -> Engine:
        """
        Devuelve el Engine.

        No devuelve una conexión abierta permanente.
        """
        return self._connect()

    def exec_string(
        self,
        sql: str,
        params: Mapping[str, Any] | None = None,
    ) -> int:
        """
        Ejecuta SQL arbitrario.

        El SQL debe proceder de una fuente confiable.
        Para valores variables usar params.
        """
        return self.exec(text(sql), params)

    def exec(
        self,
        sql: TextClause,
        params: Mapping[str, Any] | None = None,
    ) -> int:
        """
        Ejecuta una sentencia dentro de una transacción.

        Devuelve el rowcount reportado por el driver.
        """
        engine = self._connect()

        with engine.begin() as connection:
            result = connection.execute(
                sql,
                dict(params or {}),
            )
            return result.rowcount

    def close(self) -> None:
        """
        Libera el pool de conexiones.
        """
        if self.engine is not None:
            self.engine.dispose()
            self.engine = None

    def __enter__(self) -> Connection:
        self._connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
#+end_src

---

/Ejemplo de uso/

#+begin_src python
from sqlalchemy import text

settings = Settings(
    host="localhost",
    port=5432,
    database="bitr",
    user="bitr",
    password="secret",
    sslmode="prefer",
)

with Connection(settings) as db:
    customers = db.search(
        fields=["id", "name", "active"],
        model="public.customer",
        domain=[
            ("active", "=", True),
            ("id", "IN", [1, 2, 3]),
        ],
    )

    db.exec(
        text(
            """
            UPDATE public.customer
            SET active = :active
            WHERE id = :id
            """
        ),
        {
            "active": False,
            "id": 10,
        },
    )
