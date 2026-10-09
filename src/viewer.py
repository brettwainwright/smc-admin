import polars as pl
import streamlit as st
from sqlalchemy import select

from src.db import engine
from src.models import Event, EventType, Location, Schedule, Volunteer
from src.models.index import format_day

TIME_FORMAT = "%-I:%M %p"  # 4:30 PM, matches format_time in src/models/index.py


def load_volunteers() -> pl.DataFrame:
    stmt = select(Volunteer.id, Volunteer.first, Volunteer.last).order_by(Volunteer.last, Volunteer.first)
    return pl.read_database(stmt, connection=engine).with_columns(
        pl.concat_str("first", "last", separator=" ").alias("name")
    )


def load_events(volunteer_id: int) -> pl.DataFrame:
    stmt = (
        select(
            Event.day,
            Event.start,
            Event.end,
            Event.name.label("event"),
            EventType.name.label("type"),
            Location.name.label("location"),
            Event.details,
        )
        .select_from(Event)
        .join(Event.location)
        .outerjoin(Event.type)
        .join(Event.schedules)
        .join(Schedule.volunteers)
        .where(Volunteer.id == volunteer_id)
    )
    df = pl.read_database(stmt, connection=engine)
    if df.is_empty():
        return df
    return (
        # unique(): the same event can be on more than one of their schedules
        df.unique()
        .sort("day", "start")
        .with_columns(
            pl.format(
                "{} – {}",
                pl.col("start").dt.strftime(TIME_FORMAT),
                pl.col("end").dt.strftime(TIME_FORMAT),
            ).alias("time")
        )
    )


st.title("SMC Volunteer Schedule")

# Pinned to the bottom of the page; images are served from src/photos via the /photos mount in main.py
with st.bottom:
    map_col, schedule_col = st.columns(2)
    map_col.link_button("🗺️ View map", "/photos/map.jpeg", width="stretch")
    schedule_col.link_button("📅 View full schedule", "/photos/schedule.jpeg", width="stretch")

volunteers = load_volunteers()
if volunteers.is_empty():
    st.info("No volunteers have signed up yet.")
    st.stop()

names = dict(volunteers.select("id", "name").iter_rows())
volunteer_id = st.selectbox(
    "Find your schedule",
    options=list(names),
    format_func=names.get,
    index=None,
    placeholder="Choose your name",
)
if volunteer_id is None:
    st.stop()

events = load_events(volunteer_id)
if events.is_empty():
    st.info("You're not scheduled for any events yet.")
    st.stop()

st.caption(f"{events.height} event{'s' if events.height != 1 else ''}")

# Sorted by day then start, so filtering per day keeps events in time order
for day in events["day"].unique(maintain_order=True):
    st.subheader(format_day(day))
    for event in events.filter(pl.col("day") == day).iter_rows(named=True):
        with st.container(border=True):
            title_col, type_col = st.columns([3, 1], vertical_alignment="center")
            title_col.markdown(f"#### {event['event']}")
            if event["type"]:
                with type_col:
                    st.badge(event["type"], color="blue")
            st.markdown(
                f":material/schedule: **{event['time']}**  \n"
                f":material/location_on: {event['location']}"
            )
            if event["details"]:
                st.caption(event["details"])
