# Streamlit + SQLAlchemy + SQLiteCloud Starter

Starter template wiring up **Streamlit** with **SQLAlchemy**, **SQLAdmin**, and **SQLiteCloud**.

## Stack

- **Streamlit** — frontend via `st.App` (ASGI)
- **SQLAlchemy 2.0** — ORM with typed mapped classes
- **SQLAdmin** ([smithyhq/sqladmin](https://github.com/smithyhq/sqladmin)) — admin UI at `/admin/` with session auth
- **SQLiteCloud** — persistent cloud-hosted SQLite (or local SQLite for dev)

## Setup

```bash
uv sync
```

## Configure

Create `.streamlit/secrets.toml` (gitignored) with your database connection string:

```toml
[database]
url = "sqlitecloud://user:pass@host:port/dbname?apikey=xxx"
```

For local dev, use plain SQLite:

```toml
[database]
url = "sqlite:///db.sqlite"
```

## Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8502
```

- **Streamlit app** — [http://localhost:8502](http://localhost:8502)
- **Admin panel** — [http://localhost:8502/admin/](http://localhost:8502/admin/)
  - Default credentials: `admin` / `admin`

## Project structure

```
main.py                # Entrypoint — creates st.App, mounts SQLAdmin at /admin
src/
  index.py             # Streamlit page — queries DB via SessionLocal
  db.py                # SQLAlchemy engine + session factory, auto-creates tables
  admin.py             # SQLAdmin config — auth backend, ModelView registrations
  models/
    index.py           # SQLAlchemy model definitions (extend Base)
    __init__.py        # Re-exports models and Base
.streamlit/
  secrets.toml         # Database connection string (gitignored)
piccolo_conf.py        # (removed — no longer used)
```

## Adding a model

1. Define the model in `src/models/index.py`:

    ```python
    class Project(Base):
        __tablename__ = "project"

        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str] = mapped_column()
    ```

2. Re-export from `src/models/__init__.py`:

    ```python
    from src.models.index import Base, Task, Project
    __all__ = ["Base", "Task", "Project"]
    ```

3. Register an admin view in `src/admin.py`:

    ```python
    from src.models import Project

    class ProjectAdmin(ModelView, model=Project):
        column_list = [Project.id, Project.name]
    ```

    Then add it inside `create_admin()`:

    ```python
    admin.add_view(ProjectAdmin)
    ```

4. Tables are auto-created on startup via `Base.metadata.create_all(engine)` in `src/db.py`.

## Customizing auth

Admin authentication is defined in `src/admin.py` via the `AdminAuth` class. The default uses hardcoded credentials. To use a real user table or external auth provider, update the `login()` and `authenticate()` methods.

The `secret_key` in `AdminAuth` is used to sign session cookies — change it to a real secret before deploying.

## Querying data in Streamlit

Use `SessionLocal` from `src/db.py` in your Streamlit pages:

```python
from sqlalchemy import select
from src.db import SessionLocal
from src.models import Task

with SessionLocal() as session:
    tasks = session.execute(select(Task)).scalars().all()
```
