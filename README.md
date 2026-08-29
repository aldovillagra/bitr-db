# bitr-db

DB globally settings and connection

## 🚀 Crear entorno

```bash
uv venv
direnv allow

## Ejecutar test

```bash
uv sync --extra postgres
uv sync --extra mysql
uv sync --extra mariadb
uv sync --extra all
uv run pytest

## Ejecutar la app

```bash
uv run python -m bitr_db
