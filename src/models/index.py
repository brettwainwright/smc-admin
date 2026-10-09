from markupsafe import Markup
from sqlalchemy import CheckConstraint, Column, ForeignKey, Table, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship
from datetime import date, datetime, time, timedelta

# Allowed range for event and availability days (inclusive)
EVENT_FIRST_DAY = date(2027, 1, 2)
EVENT_LAST_DAY = date(2027, 1, 5)
EVENT_DAYS = [
    EVENT_FIRST_DAY + timedelta(days=n)
    for n in range((EVENT_LAST_DAY - EVENT_FIRST_DAY).days + 1)
]


def in_event_days(column: str) -> str:
    return f"{column} BETWEEN '{EVENT_FIRST_DAY.isoformat()}' AND '{EVENT_LAST_DAY.isoformat()}'"


def format_day(d: date) -> str:
    return f"{d:%a %b} {d.day}"  # Sat Jan 2


def format_time(t: time) -> str:
    return f"{t.hour % 12 or 12}:{t:%M %p}"  # 4:30 PM

class Base(DeclarativeBase):
    pass


# Many-to-many link: a schedule has many volunteers, a volunteer can be on many schedules
schedule_volunteer = Table(
    "schedule_volunteer",
    Base.metadata,
    Column("schedule_id", ForeignKey("schedule.id", ondelete="CASCADE"), primary_key=True),
    Column("volunteer_id", ForeignKey("volunteer.id", ondelete="CASCADE"), primary_key=True),
)


class EventType(Base):
    __tablename__ = "event_type"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(unique=True)

    events: Mapped[list["Event"]] = relationship(back_populates="type")

    def __str__(self) -> str:
        return self.name


class Location(Base):
    __tablename__ = "location"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(unique=True)

    events: Mapped[list["Event"]] = relationship(back_populates="location")

    def __str__(self) -> str:
        return self.name


class Event(Base):
    __tablename__ = 'event'
    __table_args__ = (
        CheckConstraint(in_event_days("day"), name="ck_event_day_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    day: Mapped[date]
    start: Mapped[time]
    end: Mapped[time]
    name: Mapped[str]
    # Nullable so events that existed before types were added stay valid
    type_id: Mapped[int | None] = mapped_column(ForeignKey("event_type.id", ondelete="SET NULL"))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"))
    description: Mapped[str | None]
    details: Mapped[str | None]

    # Eager-loaded so it's still available after sqladmin closes the session
    type: Mapped[EventType | None] = relationship(back_populates="events", lazy="joined")
    location: Mapped[Location] = relationship(back_populates="events", lazy="joined")
    schedules: Mapped[list["Schedule"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )

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
    def display(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        name = f"{self.description} · " if self.description else ""
        return f"{name}{self.when} @ {self.location}"


class Volunteer(Base):
    __tablename__ = "volunteer"
    __table_args__ = (
        CheckConstraint(in_event_days("availability_start"), name="ck_volunteer_start_range"),
        CheckConstraint(in_event_days("availability_end"), name="ck_volunteer_end_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    first: Mapped[str]
    last: Mapped[str]
    email: Mapped[str] = mapped_column(server_default="test@email.com")
    phone: Mapped[str] = mapped_column(server_default="999999999")
    availability_start: Mapped[date]
    availability_end: Mapped[date]
    start_time: Mapped[time]
    end_time: Mapped[time]

    schedules: Mapped[list["Schedule"]] = relationship(
        secondary=schedule_volunteer, back_populates="volunteers"
    )

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
    def scheduled(self) -> list[Markup]:
        return [
            Markup("<strong>{}</strong> · {} @ {}").format(s.event.description or "Untitled event", s.event.when, s.event.location)
            for s in self.schedules
        ]

    def __str__(self) -> str:
        return f"{self.first} {self.last}"


class Schedule(Base):
    __tablename__ = "schedule"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id", ondelete="CASCADE"))

    event: Mapped[Event] = relationship(back_populates="schedules", lazy="joined")
    volunteers: Mapped[list[Volunteer]] = relationship(
        secondary=schedule_volunteer, back_populates="schedules"
    )

    def __str__(self) -> str:
        return f"{self.event}"


def _schedule_event(session: Session, schedule: Schedule) -> Event | None:
    # sqladmin sets event_id directly, so the event relationship can be unset or stale until flush
    if schedule.event is not None and schedule.event.id == schedule.event_id:
        return schedule.event
    return session.get(Event, schedule.event_id) if schedule.event_id is not None else None


@event.listens_for(Session, "before_flush")
def check_volunteer_availability(session: Session, flush_context, instances) -> None:
    """Reject saves that put a volunteer on an event outside their availability.

    Runs for every save, so it covers new/edited schedules, volunteers whose availability
    changed, and events whose day/time changed. sqladmin shows the error on the form.
    """
    pairs: set[tuple[Volunteer, Event]] = set()
    with session.no_autoflush:
        for obj in session.new | session.dirty:
            if isinstance(obj, Schedule):
                ev = _schedule_event(session, obj)
                if ev is not None:
                    pairs.update((v, ev) for v in obj.volunteers)
            elif isinstance(obj, Volunteer):
                pairs.update(
                    (obj, ev) for s in obj.schedules if (ev := _schedule_event(session, s)) is not None
                )
            elif isinstance(obj, Event):
                pairs.update((v, obj) for s in obj.schedules for v in s.volunteers)

        problems = sorted(
            f"{v.full_name} isn't available for {ev} (available {v.availability})."
            for v, ev in pairs
            if not v.is_available_for(ev)
        )
    if problems:
        raise ValueError(" ".join(problems))
