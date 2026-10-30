import random
from datetime import date, time

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from schedule.models import EVENT_DAYS, Event, EventType, Location, Volunteer

# All mock data is made up: example.com emails and 555-01xx phone numbers are reserved for fiction.
# Locations and sessions mirror the placeholder map.jpeg / schedule.jpeg.
LOCATIONS = ["Main Hall", "Breakout A", "Breakout B", "Encounter Rooms", "Check In", "SMC Store", "Gym"]

FIRST_NAMES = [
    "Avery", "Jordan", "Riley", "Morgan", "Casey", "Taylor", "Quinn", "Skyler", "Jamie", "Rowan",
    "Parker", "Hayden", "Emerson", "Reese", "Dakota", "Finley", "Sawyer", "Logan", "Peyton", "Cameron",
    "Elliot", "Harper", "Kendall", "Blake", "Drew", "Sage", "Remy", "Jesse", "Shawn", "Lane",
]
LAST_NAMES = [
    "Adams", "Brooks", "Carter", "Diaz", "Ellis", "Foster", "Garcia", "Hughes", "Irwin", "James",
    "Kim", "Lopez", "Morris", "Nguyen", "Ortiz", "Patel", "Reed", "Shaw", "Turner", "Vance",
]

# (day index, start, end, name, type, location, description, details, volunteers needed)
EVENTS = [
    (0, time(13, 0), time(18, 0), "Check In", "Check In", "Check In",
     "Greet students and hand out welcome packets.", "Arrive 15 minutes early for a briefing.", 6),
    (0, time(13, 0), time(17, 0), "SMC Store Setup", "SMC Store", "SMC Store",
     "Unpack and display merch.", "", 3),
    (0, time(18, 30), time(21, 0), "Main Session 1", "Main Session", "Main Hall",
     "Usher and help with seating.", "Doors open 6:30 PM.", 8),
    (0, time(21, 30), time(0, 30), "Night Life", "Night Life", "Gym",
     "Supervise games and snacks.", "Runs past midnight.", 5),
    (1, time(8, 30), time(10, 30), "Main Session 2", "Main Session", "Main Hall",
     "Usher and help with seating.", "", 8),
    (1, time(8, 30), time(10, 30), "Check Wristbands", "Check Wristbands", "Main Hall",
     "Check wristbands at the doors.", "", 4),
    (1, time(11, 0), time(12, 0), "Breakout: Leadership", "Breakout", "Breakout A",
     "Room host for the leadership breakout.", "", 2),
    (1, time(11, 0), time(12, 0), "Breakout: Worship Team", "Breakout", "Breakout B",
     "Room host for the worship team breakout.", "", 2),
    (1, time(13, 0), time(16, 0), "Basketball Tournament", "Basketball Tournament", "Gym",
     "Keep score and run brackets.", "", 4),
    (1, time(13, 0), time(17, 0), "SMC Store", "SMC Store", "SMC Store",
     "Run the register.", "", 3),
    (1, time(18, 30), time(21, 0), "Main Session 3", "Main Session", "Main Hall",
     "Usher and help with seating.", "", 8),
    (1, time(21, 15), time(23, 0), "Encounter", "Encounter", "Encounter Rooms",
     "Prayer team and room hosts.", "", 6),
    (2, time(8, 30), time(10, 30), "Main Session 4", "Main Session", "Main Hall",
     "Usher and help with seating.", "", 8),
    (2, time(11, 0), time(12, 0), "Breakout: Missions", "Breakout", "Breakout A",
     "Room host for the missions breakout.", "", 2),
    (2, time(11, 0), time(12, 0), "Breakout: College Life", "Breakout", "Breakout B",
     "Room host for the college life breakout.", "", 2),
    (2, time(13, 0), time(17, 0), "SMC Store", "SMC Store", "SMC Store",
     "Run the register.", "", 3),
    (2, time(18, 30), time(21, 0), "Main Session 5", "Main Session", "Main Hall",
     "Usher and help with seating.", "", 8),
    (2, time(21, 30), time(0, 30), "Night Life", "Night Life", "Gym",
     "Supervise games and snacks.", "Runs past midnight.", 5),
    (3, time(8, 30), time(10, 30), "Main Session 6", "Main Session", "Main Hall",
     "Usher and help with seating.", "", 8),
    (3, time(10, 30), time(12, 0), "Kaleo Interest Form", "Kaleo Interest Form", "Main Hall",
     "Staff the Kaleo table and collect interest forms.", "", 3),
]


def mock_availability(rng: random.Random) -> tuple[date, time, date, time]:
    """Mostly whole-event volunteers, plus some who can only do a stretch of days."""
    first, last = 0, len(EVENT_DAYS) - 1
    if rng.random() < 0.6:
        return EVENT_DAYS[first], time(8, 0), EVENT_DAYS[last], time(14, 0)
    start = rng.randint(first, last - 1)
    end = rng.randint(start + 1, last)
    return EVENT_DAYS[start], rng.choice([time(8, 0), time(12, 0)]), EVENT_DAYS[end], rng.choice([time(14, 0), time(23, 59)])


class Command(BaseCommand):
    help = "Fill the database with made-up locations, events, volunteers, and assignments for development"

    def add_arguments(self, parser):
        parser.add_argument("--volunteers", type=int, default=60, help="How many volunteers to create (default 60)")
        parser.add_argument("--seed", type=int, default=2027, help="Random seed, for repeatable data")
        parser.add_argument(
            "--reset", action="store_true",
            help="Delete all existing locations, events, and volunteers first (event types are kept)",
        )

    @transaction.atomic
    def handle(self, *args, volunteers: int, seed: int, reset: bool, **options):
        if reset:
            Event.objects.all().delete()
            Volunteer.objects.all().delete()
            Location.objects.all().delete()
        elif Event.objects.exists() or Volunteer.objects.exists():
            raise CommandError("The database already has events or volunteers. Use --reset to replace them.")

        rng = random.Random(seed)
        types = {t.name: t for t in EventType.objects.all()}
        locations = {name: Location.objects.create(name=name) for name in LOCATIONS}

        names = rng.sample([(f, l) for f in FIRST_NAMES for l in LAST_NAMES], volunteers)
        people = []
        for n, (first, last) in enumerate(names):
            start_day, start_time, end_day, end_time = mock_availability(rng)
            people.append(Volunteer(
                first=first, last=last,
                email=f"{first}.{last}{n}@example.com".lower(),
                phone=f"555-01{n % 100:02d}",
                availability_start=start_day, start_time=start_time,
                availability_end=end_day, end_time=end_time,
            ))
        people = Volunteer.objects.bulk_create(people)

        assigned = 0
        booked: dict[int, list[Event]] = {v.pk: [] for v in people}
        for day, start, end, name, type_name, location, description, details, needed in EVENTS:
            event = Event.objects.create(
                day=EVENT_DAYS[day], start=start, end=end, name=name, type=types.get(type_name),
                location=locations[location], description=description, details=details, needed=needed,
            )
            # Only people who are available and not already on an overlapping event, so the checks pass.
            # Some events are deliberately left a person or two short so the staffing views have work to show.
            free = [v for v in people if v.is_available_for(event) and not any(event.overlaps(b) for b in booked[v.pk])]
            crew = rng.sample(free, min(needed - rng.choice([0, 0, 0, 1, 2]), len(free)))
            event.volunteers.add(*crew)
            for v in crew:
                booked[v.pk].append(event)
            assigned += len(crew)

        self.stdout.write(self.style.SUCCESS(
            f"Created {len(locations)} locations, {len(EVENTS)} events, {len(people)} volunteers, "
            f"and {assigned} volunteer assignments."
        ))
