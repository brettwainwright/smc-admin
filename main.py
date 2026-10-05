import streamlit as st

from starlette.routing import Mount

from src.db import engine
from src.admin import create_admin

admin = create_admin(engine, base_url="/admin")

app = st.App(
    script_path="src/index.py",
    routes=[
        Mount("/admin", app=admin.admin),
    ],
)

if __name__ == "__main__":
    app.run()
