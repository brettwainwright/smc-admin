import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models import Base

# Set your connection string in .streamlit/secrets.toml:
#   [database]
#   url = "sqlitecloud://user:pass@host:port/dbname?apikey=xxx"
#
# For local dev, you can use plain SQLite:
#   url = "sqlite:///db.sqlite"

engine = create_engine(st.secrets["database"]["url"])
SessionLocal = sessionmaker(bind=engine)

Base.metadata.create_all(engine)
