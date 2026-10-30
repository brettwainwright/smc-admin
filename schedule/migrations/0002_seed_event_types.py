from django.db import migrations

EVENT_TYPES = [
    "Breakout",
    "Encounter",
    "Main Session",
    "SMC Store",
    "Check In",
    "Night Life",
    "Check Wristbands",
    "Kaleo Interest Form",
    "Basketball Tournament",
]


def seed_event_types(apps, schema_editor):
    EventType = apps.get_model("schedule", "EventType")
    for name in EVENT_TYPES:
        EventType.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("schedule", "0001_initial")]

    operations = [migrations.RunPython(seed_event_types, migrations.RunPython.noop)]
