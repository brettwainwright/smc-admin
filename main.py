import streamlit as st

from starlette.routing import Mount

from src.admin import app as admin_app
from src.signup import app as signup_app


app = st.App(
    script_path="src/viewer.py",
    routes=[
        Mount(path='/admin', app=admin_app),
        Mount(path='/signup', app=signup_app),
    ]
)

if __name__ == "__main__":
    app.run()
