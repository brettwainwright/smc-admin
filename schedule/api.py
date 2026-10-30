from django_bolt import BoltAPI, Request
from django_bolt.concurrency import sync_to_thread
from django_bolt.health import register_health_checks
from django_bolt.shortcuts import render

from schedule.models import Event, Volunteer, format_day, format_time

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

