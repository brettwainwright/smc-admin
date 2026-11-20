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


class TimeSlot(models.Model):
    """A part of an event day that volunteers sign up for (e.g. Sun Jan 3 · Afternoon)."""

    class Part(models.TextChoices):
        MORNING = "morning", "Morning"
        AFTERNOON = "afternoon", "Afternoon"
        EVENING = "evening", "Evening"

    day = models.DateField(choices=DAY_CHOICES)
    part = models.CharField(max_length=10, choices=Part.choices)
    start = models.TimeField()
    end = models.TimeField(help_text="At or before the start means it runs past midnight.")

    class Meta:
        ordering = ["day", "start"]
        constraints = [
            in_event_days("day"),
            models.UniqueConstraint(fields=["day", "part"], name="uq_timeslot_day_part"),
        ]

    @property
    def starts_at(self) -> datetime:
        return datetime.combine(self.day, self.start)

    @property
    def ends_at(self) -> datetime:
        ends_at = datetime.combine(self.day, self.end)
        # Same rule as Event: an end at or before the start runs past midnight (Evening ends at 00:00)
        return ends_at if ends_at > self.starts_at else ends_at + timedelta(days=1)

    def __str__(self) -> str:
        return f"{format_day(self.day)} · {self.get_part_display()}"


class Volunteer(models.Model):
    first = models.CharField("first name", max_length=100)
    last = models.CharField("last name", max_length=100)
    email = models.CharField(max_length=254, validators=[validate_email])
    phone = models.CharField(max_length=25, validators=[validate_phone])
    text_ok = models.BooleanField("OK to text", null=True, blank=True)

    # Availability: any number of day/part-of-day slots
    slots = models.ManyToManyField(TimeSlot, verbose_name="available slots", related_name="volunteers", blank=True)
    availability_unsure = models.BooleanField("not sure of availability yet", default=False)
    workload_preference = models.CharField(max_length=200, blank=True)

    # Scheduling notes
    physical_limitations = models.TextField(blank=True)
    previous_role_preferences = models.TextField("role preferences from previous SMCs", blank=True)
    additional_info = models.TextField("additional information", blank=True)
    comments = models.TextField(blank=True)

    # Background
    volunteered_before = models.BooleanField("volunteered at SMC before", null=True, blank=True)
    tech_comfortable = models.BooleanField("comfortable with technology", null=True, blank=True)
    relationship = models.CharField("best describes them", max_length=100, blank=True)
    invited_by = models.CharField("invited by (staff)", max_length=200, blank=True)
    registered_at = models.DateTimeField("registered", null=True, blank=True)

    # Demographics and mailing address
    gender = models.CharField(max_length=20, blank=True)
    age_range = models.CharField(max_length=20, blank=True)
    street1 = models.CharField("street", max_length=200, blank=True)
    street2 = models.CharField("street 2", max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["last", "first"]
        # The registration import matches people on all three (families can share an email)
        constraints = [models.UniqueConstraint(fields=["first", "last", "email"], name="uq_volunteer_name_email")]

    @property
    def full_name(self) -> str:
        return f"{self.first} {self.last}"

    @property
    def availability(self) -> str:
        """Sat Jan 2: Afternoon, Evening · Sun Jan 3: Morning"""
        by_day: dict[date, list[str]] = {}
        for slot in sorted(self.slots.all(), key=lambda s: s.starts_at):
            by_day.setdefault(slot.day, []).append(slot.get_part_display())
        summary = " · ".join(f"{format_day(d)}: {', '.join(parts)}" for d, parts in by_day.items()) or "No slots"
        return f"{summary} (unsure)" if self.availability_unsure else summary

    def available_windows(self, slots=None) -> list[tuple[datetime, datetime]]:
        """The volunteer's slots (or the given ones) merged into continuous stretches,
        so back-to-back slots like Morning + Afternoon count as one."""
        windows: list[list[datetime]] = []
        for slot in sorted(self.slots.all() if slots is None else slots, key=lambda s: s.starts_at):
            if windows and slot.starts_at <= windows[-1][1]:
                windows[-1][1] = max(windows[-1][1], slot.ends_at)
            else:
                windows.append([slot.starts_at, slot.ends_at])
        return [(start, end) for start, end in windows]

    def is_available_for(self, event: Event, slots=None) -> bool:
        return any(start <= event.starts_at and event.ends_at <= end for start, end in self.available_windows(slots))

    @property
    def contact_info(self) -> str:
        return f"Email: {self.email} Phone: {self.phone}"

    @property
    def scheduled(self) -> list[str]:
        return [
            format_html("<strong>{}</strong> · {} @ {}", ev.name or "Untitled event", ev.when, ev.location)
            for ev in self.events.select_related("location")
        ]

    def availability_problems(self, slots=None) -> list[str]:
        """Events this volunteer is already on that fall outside their slots (or the given, possibly unsaved, ones)."""
        if self.pk is None:
            return []
        slots = list(self.slots.all() if slots is None else slots)
        return sorted(
            f"{self.full_name} is on {ev}, which those slots don't cover."
            for ev in self.events.select_related("location")
            if not self.is_available_for(ev, slots)
        )

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
