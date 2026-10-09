import secrets
from typing import Any
import streamlit as st
from pathlib import Path

from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from datetime import date

from wtforms import SelectField

from src.db import engine
from src.models.validators import email_validators, phone_validators
from src.models import Event, EventType, Location, Schedule, Volunteer
from src.models.index import EVENT_DAYS


def to_date(value):
    # Form posts send "YYYY-MM-DD" strings; loaded records already hold a date
    return value if isinstance(value, date) else date.fromisoformat(value)


# form_args for any date column restricted to EVENT_DAYS.
# Returns a fresh dict each call since sqladmin mutates form_args entries.
def day_select_args():
    return {
        "choices": [(d, d.isoformat()) for d in EVENT_DAYS],
        "coerce": to_date,
    }


def available_volunteers_by_event() -> dict[str, list[str]]:
    # Keys and values are strings to match the <option> values in the schedule form
    with Session(engine) as session:
        events = session.scalars(select(Event)).all()
        volunteers = session.scalars(select(Volunteer)).all()
        return {
            str(e.id): [str(v.id) for v in volunteers if v.is_available_for(e)]
            for e in events
        }


class AdminAuth(AuthenticationBackend):
    username: str
    password: str

    def __init__(self, secret_key: str | None, username: str | None, password: str | None, **session_kwargs: Any) -> None:

        if secret_key is None:
            raise ValueError('No secret key found')

        if username is None:
            raise ValueError('No username found')

        if password is None:
            raise ValueError('No password found')

        self.secret_key = secret_key
        self.username = username
        self.password = password

        super().__init__(secret_key, **session_kwargs)

        

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))
        valid = secrets.compare_digest(username, self.username) & secrets.compare_digest(password, self.password)
        if valid:
            request.session.update({"authenticated": True})
        return valid

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return request.session.get("authenticated", False)


class LocationAdmin(ModelView, model=Location):
    column_list = [Location.name]
    column_searchable_list = [Location.name]
    column_sortable_list = [Location.name]
    column_default_sort = [("name", False)]
    form_excluded_columns = [Location.events]


class EventTypeAdmin(ModelView, model=EventType):
    column_list = [EventType.name]
    column_searchable_list = [EventType.name]
    column_sortable_list = [EventType.name]
    column_default_sort = [("name", False)]
    form_excluded_columns = [EventType.events]


class EventAdmin(ModelView, model=Event):
    column_list = [
        Event.name,
        Event.type,
        "when",
        Event.location,
        Event.description
    ]
    column_searchable_list = [Event.description, "location.name"]
    column_sortable_list = [Event.day, Event.start]
    form_excluded_columns = [Event.schedules]
    form_overrides = {"day": SelectField}
    form_args = {"day": day_select_args()}
    page_size = 75


class VolunteerAdmin(ModelView, model=Volunteer):
    column_list = [
        "full_name",
        "availability",
        Volunteer.schedules
    ]
    column_searchable_list = ["full_name"]
    column_sortable_list = [Volunteer.first, Volunteer.availability_start]
    show_compact_lists = False
    column_details_list = [
        "full_name",
        "contact_info",
        "availability",
        Volunteer.schedules,
    ]
    column_labels = {
        "full_name": "name",
        "contact_info": 'contact info',
        "availability": "availability",
        Volunteer.schedules: "scheduled",
    }
    column_formatters_detail = {
        Volunteer.schedules: lambda m, a: m.scheduled,
    }
    form_excluded_columns = [Volunteer.schedules]
    form_overrides = {"availability_start": SelectField, "availability_end": SelectField}
    form_args = {
        "first": {"label": "First name"},
        "last": {"label": "Last name"},
        "availability_start": {**day_select_args(), "label": "Available from"},
        "start_time": {"label": "Start time"},
        "availability_end": {**day_select_args(), "label": "Available until"},
        "end_time": {"label": "End time"},
        "email": {"validators": email_validators()},
        "phone": {"validators": phone_validators()},
    }
    page_size = 50


class ScheduleAdmin(ModelView, model=Schedule):
    column_list = [Schedule.event, Schedule.volunteers]
    column_default_sort = [("event.day", False), ("event.start", False)]
    form_columns = [Schedule.event, Schedule.volunteers]
    page_size = 150
    # These add a script that narrows the volunteer list to people available for the chosen event
    create_template = "schedule_create.html"
    edit_template = "schedule_edit.html"
    save_as = True
    name_plural = 'Master Schedule'

    async def create_context(self, request: Request) -> dict[str, Any]:
        return {"available_volunteers": await run_in_threadpool(available_volunteers_by_event)}

    async def edit_context(self, request: Request) -> dict[str, Any]:
        return {"available_volunteers": await run_in_threadpool(available_volunteers_by_event)}



username = st.secrets.get('username', None)
password = st.secrets.get('password', None)
secret_key = st.secrets.get('secret_key', None)

app = Starlette()
admin = Admin(
    app=app,
    engine=engine,
    base_url='/',
    templates_dir=str(Path(__file__).parent / "templates"),
    title="SMC Admin",
    debug=True,
    authentication_backend=AdminAuth(secret_key=secret_key, username=username, password=password),
)
admin.add_view(LocationAdmin)
admin.add_view(EventTypeAdmin)
admin.add_view(EventAdmin)
admin.add_view(VolunteerAdmin)
admin.add_view(ScheduleAdmin)



