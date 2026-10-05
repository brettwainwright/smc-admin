from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.applications import Starlette
from starlette.requests import Request

from src.models import Task


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        # Replace with real credential check
        if username == "admin" and password == "admin":
            request.session.update({"authenticated": True})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return request.session.get("authenticated", False)


class TaskAdmin(ModelView, model=Task):
    column_list = [Task.id, Task.name, Task.completed]


def create_admin(engine, base_url: str = "/admin") -> Admin:
    _app = Starlette()
    admin = Admin(
        _app,
        engine,
        base_url=base_url,
        title="Admin",
        authentication_backend=AdminAuth(secret_key="change-me-to-a-real-secret"),
    )
    admin.add_view(TaskAdmin)
    return admin
