import streamlit as st
from sqlalchemy import select

from src.db import SessionLocal
from src.models import Schedule


st.title("My App")


