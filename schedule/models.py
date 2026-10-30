from datetime import date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.html import format_html

from schedule.validators import validate_email, validate_phone

# Allowed range for event and availability days (inclusive)
EVENT_FIRST_DAY = date(2027, 1, 2)
EVENT_LAST_DAY = date(2027, 1, 5)
EVENT_DAYS = [
    EVENT_FIRST_DAY + timedelta(days=n)
    for n in range((EVENT_LAST_DAY - EVENT_FIRST_DAY).days + 1)
]


def format_day(d: date) -> str:
    return f"{d:%a %b} {d.day}"  # Sat Jan 2


def format_time(t: time) -> str:
    return f"{t.hour % 12 or 12}:{t:%M %p}"  # 4:30 PM


# Admin and forms render these date fields as a select of the event days
DAY_CHOICES = [(d, format_day(d)) for d in EVENT_DAYS]


def in_event_days(field: str) -> models.CheckConstraint:
    return models.CheckConstraint(
        condition=Q(**{f"{field}__range": (EVENT_FIRST_DAY, EVENT_LAST_DAY)}),
        name=f"ck_%(class)s_{field}_range",
    )


class EventType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Location(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Event(models.Model):
    day = models.DateField(choices=DAY_CHOICES)
    start = models.TimeField()
    end = models.TimeField()
    name = models.CharField(max_length=200)
    type = models.ForeignKey(EventType, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="events")
    description = models.TextField(blank=True)
    details = models.TextField(blank=True)
    needed = models.PositiveSmallIntegerField("volunteers needed", default=1)
    volunteers = models.ManyToManyField("Volunteer", related_name="events", blank=True)

    class Meta:
        ordering = ["day", "start"]
        constraints = [in_event_days("day")]
        verbose_name_plural = "SMC Schedule"

    @property
    def when(self) -> str:
        return f"{format_day(self.day)} · {format_time(self.start)}–{format_time(self.end)}"

    @property
    def starts_at(self) -> datetime:
        return datetime.combine(self.day, self.start)

    @property
    def ends_at(self) -> datetime:
        ends_at = datetime.combine(self.day, self.end)
        # An end time at or before the start means the event runs past midnight
        return ends_at if ends_at > self.starts_at else ends_at + timedelta(days=1)

    @property
    def hours(self) -> float:
        return (self.ends_at - self.starts_at).total_seconds() / 3600

    def overlaps(self, other: "Event") -> bool:
        return self.starts_at < other.ends_at and other.starts_at < self.ends_at

    def __str__(self) -> str:
        return f"{self.name} · {self.when} @ {self.location}"


class Volunteer(models.Model):
    first = models.CharField("first name", max_length=100)
    last = models.CharField("last name", max_length=100)
    email = models.CharField(max_length=254, validators=[validate_email])
    phone = models.CharField(max_length=25, validators=[validate_phone])
    availability_start = models.DateField("available from", choices=DAY_CHOICES)
    start_time = models.TimeField()
    availability_end = models.DateField("available until", choices=DAY_CHOICES, default=EVENT_LAST_DAY)
    end_time = models.TimeField()

    class Meta:
        ordering = ["last", "first"]
        constraints = [in_event_days("availability_start"), in_event_days("availability_end")]

    @property
    def full_name(self) -> str:
        return f"{self.first} {self.last}"

    @property
    def availability(self) -> str:
        start = f"{format_day(self.availability_start)}, {format_time(self.start_time)}"
        end = f"{format_day(self.availability_end)}, {format_time(self.end_time)}"
        return f"{start} → {end}"

    @property
    def available_from(self) -> datetime:
        return datetime.combine(self.availability_start, self.start_time)

    @property
    def available_until(self) -> datetime:
        return datetime.combine(self.availability_end, self.end_time)

    def is_available_for(self, event: Event) -> bool:
        return self.available_from <= event.starts_at and event.ends_at <= self.available_until

    @property
    def contact_info(self) -> str:
        return f"Email: {self.email} Phone: {self.phone}"

    @property
    def scheduled(self) -> list[str]:
        return [
            format_html("<strong>{}</strong> · {} @ {}", ev.name or "Untitled event", ev.when, ev.location)
            for ev in self.events.select_related("location")
        ]

    def availability_problems(self) -> list[str]:
        # Events this volunteer is already on, checked against their (possibly edited) availability
        if self.pk is None or None in (self.availability_start, self.availability_end, self.start_time, self.end_time):
            return []
        return availability_problems((self, ev) for ev in self.events.select_related("location"))

    def clean(self) -> None:
        if (
            None not in (self.availability_start, self.availability_end, self.start_time, self.end_time)
            and self.available_until <= self.available_from
        ):
            raise ValidationError({"end_time": "Availability must end after it starts."})
        if problems := self.availability_problems():
            raise ValidationError(" ".join(problems))

    def __str__(self) -> str:
        return f"{self.first} {self.last}"


def assignment_problems(event: Event, volunteers) -> list[str]:
    """Why these volunteers can't work this event (using its current, possibly unsaved, times):
    it's outside their availability, or it overlaps another event they're already on."""
    volunteers = list(volunteers)
    problems = availability_problems((v, event) for v in volunteers)
    # Their other events; the event itself is excluded so editing its own times isn't a clash
    links = (
        Event.volunteers.through.objects.filter(volunteer__in=volunteers)
        .exclude(event_id=event.pk)
        .select_related("volunteer", "event__location")
    )
    problems += [
        f"{link.volunteer.full_name} is already on {link.event} at that time."
        for link in links
        if link.event.overlaps(event)
    ]
    return sorted(set(problems))


def availability_problems(pairs) -> list[str]:
    """Messages for each (volunteer, event) pair where the event falls outside their availability."""
    return sorted(
        f"{v.full_name} isn't available for {ev} (available {v.availability})."
        for v, ev in set(pairs)
        if not v.is_available_for(ev)
    )
