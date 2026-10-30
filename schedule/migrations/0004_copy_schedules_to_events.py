from django.db import migrations


def copy_schedules_to_events(apps, schema_editor):
    """Move each Schedule's volunteers onto its event, before the Schedule model is removed."""
    Event = apps.get_model("schedule", "Event")
    for event in Event.objects.prefetch_related("schedules__volunteers"):
        volunteers = {v for s in event.schedules.all() for v in s.volunteers.all()}
        event.volunteers.add(*volunteers)
        # Existing events start out fully staffed; adjust "needed" in the admin afterwards
        event.needed = max(1, len(volunteers))
        event.save(update_fields=["needed"])


class Migration(migrations.Migration):
    dependencies = [("schedule", "0003_event_volunteers_needed")]

    operations = [migrations.RunPython(copy_schedules_to_events, migrations.RunPython.noop)]
