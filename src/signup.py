import secrets
from datetime import date, datetime
from pathlib import Path

import streamlit as st
from sqlalchemy.orm import Session
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates
from wtforms import EmailField, Form, SelectField, StringField, TelField, TimeField
from wtforms.validators import DataRequired, InputRequired, Length

from src.db import engine
from src.models import Volunteer
from src.models.validators import email_validators, phone_validators
from src.models.index import EVENT_DAYS


templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

SIGNUP_KEY = st.secrets.get("signup_key", None)
if not SIGNUP_KEY:
    raise ValueError("No signup_key found")
SIGNUP_KEY = str(SIGNUP_KEY)  # compare_digest needs str on both sides; TOML may give a number


DAY_CHOICES = [(d.isoformat(), d.isoformat()) for d in EVENT_DAYS]


class SignupForm(Form):
    first = StringField("First name", validators=[DataRequired(), Length(max=100)])
    last = StringField("Last name", validators=[DataRequired(), Length(max=100)])
    email = EmailField("Email", validators=email_validators())
    phone = TelField("Phone", validators=phone_validators())
    availability_start = SelectField("Available from", choices=DAY_CHOICES)
    start_time = TimeField("Start time", validators=[InputRequired()])
    availability_end = SelectField("Available until", choices=DAY_CHOICES, default=DAY_CHOICES[-1][0])
    end_time = TimeField("End time", validators=[InputRequired()])

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        if self.start_time.data is None or self.end_time.data is None:
            return False
        start = datetime.combine(date.fromisoformat(self.availability_start.data), self.start_time.data)
        end = datetime.combine(date.fromisoformat(self.availability_end.data), self.end_time.data)
        if end <= start:
            self.end_time.errors = [*self.end_time.errors, "Availability must end after it starts."]
            return False
        return True


def render(request: Request, form: SignupForm, saved: bool = False, status_code: int = 200):
    return templates.TemplateResponse(
        request, "signup.html", {"form": form, "saved": saved}, status_code=status_code
    )


def save_volunteer(form: SignupForm) -> None:
    with Session(engine) as session:
        session.add(Volunteer(
            first=(form.first.data or "").strip(),
            last=(form.last.data or "").strip(),
            email=(form.email.data or "").strip(),
            phone=(form.phone.data or "").strip(),
            availability_start=date.fromisoformat(form.availability_start.data),
            start_time=form.start_time.data,
            availability_end=date.fromisoformat(form.availability_end.data),
            end_time=form.end_time.data,
        ))
        session.commit()


def has_valid_key(request: Request) -> bool:
    # compare_digest avoids leaking how much of the key matched via timing
    return secrets.compare_digest(request.query_params.get("signup_key", ""), SIGNUP_KEY)


async def signup(request: Request):
    # Checked on GET and POST; the form posts back to the same URL, so the key carries through
    if not has_valid_key(request):
        return HTMLResponse("This sign-up link is invalid. Please check the link you were sent.", status_code=403)

    if request.method == "GET":
        return render(request, SignupForm(), saved="saved" in request.query_params)

    form = SignupForm(await request.form())
    if not form.validate():
        return render(request, form, status_code=400)

    await run_in_threadpool(save_volunteer, form)
    # Redirect so a page refresh doesn't resubmit the form
    return RedirectResponse(request.url.include_query_params(saved=1), status_code=303)



app = Starlette(routes=[Route("/", signup, methods=["GET", "POST"])])
