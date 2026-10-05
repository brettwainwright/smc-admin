import streamlit as st
from sqlalchemy import select

from src.db import SessionLocal
from src.models import Task


st.title("My App")

with SessionLocal() as session:
    tasks = session.execute(select(Task)).scalars().all()

if tasks:
    st.dataframe(
        [{"id": t.id, "name": t.name, "completed": t.completed} for t in tasks],
        use_container_width=True,
    )
else:
    st.info("No tasks yet.")
