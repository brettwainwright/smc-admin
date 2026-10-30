"""Reject saves that put a volunteer on an event outside their availability or on two events at once.

Forms surface the same checks as field errors first (EventAdminForm.clean, Volunteer.clean);
these signals are the backstop for writes that don't go through a form.

Editing an event's times outside a form isn't re-checked against its existing volunteers: the admin
saves the event before its new volunteer list, so a pre_save check would test the times against
the old list and could wrongly fail.
"""

from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed, pre_save
from django.dispatch import receiver

from schedule.models import Event, Volunteer, assignment_problems


@receiver(pre_save, sender=Volunteer)
def check_availability(sender, instance: Volunteer, raw: bool, **kwargs) -> None:
    if not raw and (problems := instance.availability_problems()):
        raise ValidationError(" ".join(problems))


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
        problems = assignment_problems(instance, Volunteer.objects.filter(pk__in=pk_set))
    if problems:
        raise ValidationError(" ".join(sorted(set(problems))))
