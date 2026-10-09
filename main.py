from pathlib import Path

import streamlit as st

from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from src.admin import app as admin_app
from src.signup import app as signup_app


app = st.App(
    script_path="src/viewer.py",
    routes=[
        Mount(path='/admin', app=admin_app),
        Mount(path='/signup', app=signup_app),
        Mount(path='/photos', app=StaticFiles(directory=Path(__file__).parent / "src" / "photos")),
    ]
)

if __name__ == "__main__":
    app.run()
