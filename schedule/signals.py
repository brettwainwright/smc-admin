"""Reject adding a volunteer to an event outside their availability or on two events at once.

Forms surface the same checks as field errors first (EventAdminForm.clean); this signal is the
backstop for writes that don't go through a form.

Changes that could strand existing assignments aren't re-checked here:
- an event's times: the admin saves the event before its new volunteer list, so a pre_save check
  would test the times against the old list and could wrongly fail;
- a volunteer's slots: slots.set() removes old slots before adding new ones, so an m2m_changed check
  would fail mid-way. VolunteerAdminForm.clean and the import resource check slots instead.
"""

from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from schedule.models import Event, Volunteer, assignment_problems


@receiver(m2m_changed, sender=Event.volunteers.through)
def check_added_volunteers(sender, instance, action: str, reverse: bool, pk_set: set[int] | None, **kwargs) -> None:
    if action != "pre_add" or not pk_set:
        return
    if reverse:
        # volunteer.events.add(...): instance is the volunteer, pk_set the events
        events = list(Event.objects.filter(pk__in=pk_set).select_related("location"))
        problems = [p for ev in events for p in assignment_problems(ev, [instance])]
        # The new events can also clash with each other
        problems += [
            f"{instance.full_name} can't be on both {a} and {b}."
            for i, a in enumerate(events) for b in events[i + 1:]
            if a.overlaps(b)
        ]
    else:
        problems = assignment_problems(instance, Volunteer.objects.filter(pk__in=pk_set).prefetch_related("slots"))
    if problems:
        raise ValidationError(" ".join(sorted(set(problems))))
