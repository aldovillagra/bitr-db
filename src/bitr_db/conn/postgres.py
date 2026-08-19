from typing import Literal, Optional

from pydantic import BaseModel, SecretStr, computed_field


class Connection:
    def __init__(self, config: Settings):
        self.config = config
        self.url = self.config.sqlalchemy_url
        self.engine = None
        from sqlalchemy import Connection

        self.connection: Connection

    def _create_sql(self, fields, model, domains=None):
        texto = "SELECT "
        if fields == []:
            texto += "*"
        else:
            for field in fields:
                texto += field
                if field != fields[-1]:
                    texto += ", "
        texto += " FROM " + model
        params = {}
        if domains:
            texto += " WHERE "
            for domain in domains:
                if domain[2]:
                    texto += domain[0] + " " + domain[1] + " :" + domain[0]
                    params[domain[0]] = domain[2]
                else:
                    texto += domain[0] + " " + domain[1]
                if domain[0] != domains[-1][0]:
                    texto += " AND "
        if "id" in fields:
            texto += " ORDER BY id ASC"
        from sqlalchemy.sql import text

        return text(texto), params

    def _connect(self):
        if not self.engine:
            from sqlalchemy import create_engine

            self.engine = create_engine(
                self.url,
                **self.config.engine_kwargs,
            )
        if not self.connection:
            self.connection = self.engine.connect()

    def search(self, fields, model, domain):
        sql, params = self._create_sql(fields, model, domain)
        return self.read_sql(sql, params)

    def read_sql(self, SQL, parametros=None):
        self._connect()
        import pandas as pd

        return pd.read_sql(SQL, params=parametros, con=self.engine)

    def get_conn(self):
        self._connect()
        return self.engine

    def exec_string(self, sql):
        from sqlalchemy.sql import text

        self.exec(text(sql))

    def exec(self, sql):
        self._connect()
        self.connection.execute(sql)
        self.connection.commit()

    # def _get_sql(self, name):
    #     from epaodoo import env

    #     template = env.get_template(name)
    #     return text(template.render())


class Settings(BaseModel):
    """
    postgres_prod: PostgresSettings = Field(default_factory=PostgresSettings)
    """

    host: str = "localhost"
    port: int = 5432
    database: str = "postgres"
    user: str = "postgres"
    password: SecretStr = SecretStr("postgres")

    dsn: Optional[str] = ""

    # Driver / pool / tuning
    driver: Literal["psycopg", "psycopg2"] = "psycopg"

    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 1800  # segundos (30m)

    # Conectividad
    connect_timeout: int = 10  # segundos
    sslmode: str = "allow"  # disable/allow/prefer/require/verify-ca/verify-full

    pool_pre_ping: bool = True

    @computed_field
    @property
    def sqlalchemy_url(self) -> str:
        if self.dsn:
            return self.dsn

        from sqlalchemy import URL

        url = URL.create(
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
        return url.render_as_string(hide_password=False)

    @property
    def engine_kwargs(self) -> dict[str, Any]:
        return dict(
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_timeout=self.pool_timeout,
            pool_recycle=self.pool_recycle,
            pool_pre_ping=self.pool_pre_ping,
            future=True,
        )
