import secrets

from django.http import QueryDict
from django_bolt import BoltAPI, Request
from django_bolt.concurrency import sync_to_thread
from django_bolt.health import register_health_checks
from django_bolt.responses import HTML, Redirect
from django_bolt.shortcuts import render

from schedule.forms import SignupForm
from schedule.models import Event, Volunteer, format_day, format_time
from smc.env import settings

# Handlers are async and push ORM work through sync_to_thread explicitly: bolt only threads
# sync handlers whose own body visibly calls the ORM, which misses calls made via helpers.
api = BoltAPI()
# /health (liveness, used by the Docker healthcheck) and /ready (also checks the database)
register_health_checks(api)


def volunteer_options() -> list[dict]:
    return [{"id": v.pk, "name": v.full_name} for v in Volunteer.objects.only("first", "last")]


def events_for(volunteer_id: int) -> list[dict]:
    events = Event.objects.filter(volunteers=volunteer_id).select_related("type", "location").order_by("day", "start")
    return [
        {
            "day": format_day(e.day),
            "time": f"{format_time(e.start)} – {format_time(e.end)}",
            "name": e.name,
            "type": e.type.name if e.type else None,
            "location": e.location.name,
            "description": e.description,
            "details": e.details,
        }
        for e in events
    ]


@api.get("/")
async def viewer(request: Request):
    # Volunteers are rendered into the page so the picker works without a first fetch
    volunteers = await sync_to_thread(volunteer_options)
    return render(request, "schedule/viewer.html", {"volunteers": volunteers})


@api.get("/api/volunteers")
async def volunteers() -> list[dict]:
    return await sync_to_thread(volunteer_options)


@api.get("/api/volunteers/{volunteer_id}/events")
async def volunteer_events(volunteer_id: int) -> list[dict]:
    return await sync_to_thread(events_for, volunteer_id)


def has_valid_key(request: Request) -> bool:
    # compare_digest avoids leaking how much of the key matched via timing
    return secrets.compare_digest(request.query.get("signup_key", ""), settings.signup_key)


INVALID_KEY = "This sign-up link is invalid. Please check the link you were sent."


def signup_page(request: Request, form: SignupForm, saved: bool = False, status: int = 200):
    return render(request, "schedule/signup.html", {"form": form, "saved": saved}, status=status)


def save_volunteer(form: SignupForm) -> bool:
    # is_valid() runs the model's unique/constraint checks, so it hits the DB too
    if not form.is_valid():
        return False
    form.save()
    return True


# Checked on GET and POST; the form posts back to the same URL, so the key carries through
@api.get("/signup")
async def signup_form(request: Request):
    if not has_valid_key(request):
        return HTML(INVALID_KEY, status_code=403)
    return signup_page(request, SignupForm(), saved="saved" in request.query)


@api.post("/signup")
async def signup(request: Request):
    if not has_valid_key(request):
        return HTML(INVALID_KEY, status_code=403)

    form = SignupForm(QueryDict(request.body))
    if not await sync_to_thread(save_volunteer, form):
        return signup_page(request, form, status=400)

    # Redirect so a page refresh doesn't resubmit the form
    query = QueryDict(mutable=True)
    query.update({"signup_key": request.query["signup_key"], "saved": "1"})
    return Redirect(f"/signup?{query.urlencode()}", status_code=303)
