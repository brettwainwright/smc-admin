from django.templatetags.static import static
from django_bolt import BoltAPI, Request
from django_bolt.concurrency import sync_to_thread
from django_bolt.exceptions import NotFound
from django_bolt.health import register_health_checks
from django_bolt.responses import FileResponse, Redirect
from django_bolt.shortcuts import render

from schedule.models import Event, HomePageImages, Volunteer, format_day, format_time

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


def images_version() -> str:
    # Changes on each upload, so image links skip a cached old image
    images = HomePageImages.objects.filter(pk=1).first()
    return f"{images.updated:%Y%m%d%H%M%S}" if images else "0"


def viewer_context() -> dict:
    return {"volunteers": volunteer_options(), "images_version": images_version()}


def home_image_path(kind: str) -> str | None:
    images = HomePageImages.objects.filter(pk=1).first()
    image = getattr(images, kind) if images else None
    return image.path if image else None


@api.get("/")
async def viewer(request: Request):
    # Volunteers are rendered into the page so the picker works without a first fetch
    return render(request, "schedule/viewer.html", await sync_to_thread(viewer_context))


async def image_page(request: Request, kind: str, title: str):
    # A page around the image, so the browser tab shows a title instead of "map.png (1200×900)"
    src = f"/images/{kind}?v={await sync_to_thread(images_version)}"
    return render(request, "schedule/image.html", {"title": title, "src": src})


@api.get("/map")
async def map_page(request: Request):
    return await image_page(request, "map", "Map")


@api.get("/schedule")
async def schedule_page(request: Request):
    return await image_page(request, "schedule", "Full Schedule")


@api.get("/images/{kind}")
async def home_image(kind: str):
    """The uploaded map/schedule (HomePageImages), or the committed mockup until one is uploaded."""
    if kind not in HomePageImages.KINDS:
        raise NotFound()
    if path := await sync_to_thread(home_image_path, kind):
        media_type = "image/png" if path.lower().endswith(".png") else "image/jpeg"
        return FileResponse(path, media_type=media_type, headers={"Cache-Control": "max-age=300"})
    return Redirect(static(f"photos/{kind}.jpeg"), status_code=302)


@api.get("/api/volunteers")
async def volunteers() -> list[dict]:
    return await sync_to_thread(volunteer_options)


@api.get("/api/volunteers/{volunteer_id}/events")
async def volunteer_events(volunteer_id: int) -> list[dict]:
    return await sync_to_thread(events_for, volunteer_id)

