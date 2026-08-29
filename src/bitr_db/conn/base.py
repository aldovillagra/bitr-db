from __future__ import annotations

import re
from typing import Any
from collections.abc import Mapping, Sequence

import pandas as pd
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.sql.elements import TextClause

from bitr_db.conn.settings import DatabaseSettings


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


class DatabaseConnection:
    """
    API común para PostgreSQL, MySQL y MariaDB.

    El dialecto SQL lo determina el Engine de SQLAlchemy.
    """

    def __init__(self, config: DatabaseSettings):
        self.config = config
        self.engine: Engine | None = None

    def _connect(self) -> Engine:
        """
        Crea el Engine de forma lazy.
        """
        if self.engine is None:
            self.engine = create_engine(
                self.config.sqlalchemy_url,
                **self.config.engine_kwargs,
            )

        return self.engine

    def _quote_identifier(self, identifier: str) -> str:
        """
        Valida y cita un identificador usando el dialecto activo.

        PostgreSQL utilizará comillas dobles.
        MySQL/MariaDB utilizarán backticks.
        """
        if not isinstance(identifier, str):
            raise ValueError("El identificador debe ser un string")

        identifier = identifier.strip()

        if not identifier:
            raise ValueError("El identificador no puede estar vacío")

        parts = identifier.split(".")

        for part in parts:
            if not _IDENTIFIER_PATTERN.fullmatch(part):
                raise ValueError(f"Identificador SQL inválido: {identifier!r}")

        engine = self._connect()
        preparer = engine.dialect.identifier_preparer

        return ".".join(preparer.quote(part, force=True) for part in parts)

    @staticmethod
    def _validate_operator(operator: str) -> str:
        if not isinstance(operator, str):
            raise ValueError("El operador SQL debe ser un string")

        normalized = operator.strip().upper()

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
        Construye un SELECT parametrizado compatible con los tres motores.
        """
        table_sql = self._quote_identifier(model)

        if fields:
            field_sql_list = [self._quote_identifier(field) for field in fields]
            select_sql = ", ".join(field_sql_list)
        else:
            select_sql = "*"

        sql_parts = [
            f"SELECT {select_sql}",
            f"FROM {table_sql}",
        ]

        conditions: list[str] = []
        params: dict[str, Any] = {}

        for index, domain in enumerate(domains or []):
            if len(domain) != 3:
                raise ValueError(
                    "Cada dominio debe tener formato (campo, operador, valor)"
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
                    raise ValueError(f"El operador {operator} no admite None")

                conditions.append(f"{field_sql} {operator} NULL")
                continue

            if operator in {"IS", "IS NOT"}:
                raise ValueError(f"El operador {operator} requiere valor None")

            if operator in {"IN", "NOT IN"}:
                if isinstance(value, (str, bytes)):
                    raise ValueError(f"{operator} requiere una secuencia")

                try:
                    values = list(value)
                except TypeError as exc:
                    raise ValueError(f"{operator} requiere una secuencia") from exc

                if not values:
                    conditions.append("FALSE" if operator == "IN" else "TRUE")
                    continue

                placeholders: list[str] = []

                for value_index, item in enumerate(values):
                    param_name = f"p_{index}_{value_index}"
                    placeholders.append(f":{param_name}")
                    params[param_name] = item

                conditions.append(f"{field_sql} {operator} ({', '.join(placeholders)})")
                continue

            param_name = f"p_{index}"
            conditions.append(f"{field_sql} {operator} :{param_name}")
            params[param_name] = value

        if conditions:
            sql_parts.append("WHERE " + " AND ".join(conditions))

        if any(field.lower() == "id" for field in fields):
            id_sql = self._quote_identifier("id")
            sql_parts.append(f"ORDER BY {id_sql} ASC")

        return text("\n".join(sql_parts)), params

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

    def exec(
        self,
        sql: TextClause,
        params: Mapping[str, Any] | None = None,
    ) -> int:
        """
        Ejecuta una sentencia dentro de una transacción.
        """
        engine = self._connect()

        with engine.begin() as connection:
            result = connection.execute(
                sql,
                dict(params or {}),
            )
            return result.rowcount

    def exec_string(
        self,
        sql: str,
        params: Mapping[str, Any] | None = None,
    ) -> int:
        """
        Ejecuta SQL confiable y específico del motor.
        """
        return self.exec(text(sql), params)

    def get_engine(self) -> Engine:
        return self._connect()

    def close(self) -> None:
        if self.engine is not None:
            self.engine.dispose()
            self.engine = None

    def __enter__(self) -> DatabaseConnection:
        self._connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        self.close()
