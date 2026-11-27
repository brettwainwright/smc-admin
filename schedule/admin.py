import csv
from datetime import date, datetime, timedelta

from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AdminTimeWidget
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count, F, Prefetch
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from import_export.admin import ImportMixin

from schedule.models import (
    EVENT_DAYS,
    Event,
    EventType,
    HomePageImages,
    Location,
    TimeSlot,
    Volunteer,
    assignment_problems,
    format_day,
    format_time,
)
from schedule.resources import RegistrantsXLSX, VolunteerResource


def staffing_badge(count: int, needed: int) -> str:
    status = "under" if count < needed else "over" if count > needed else "full"
    return format_html('<span class="staffing staffing-{}">{} / {}</span>', status, count, needed)


def volunteer_bookings() -> dict[str, list]:
    """The events each volunteer is on ([start, end, event id]), for the event form's picker script.

    Keys are strings to match the <option> values in the volunteer <select>.
    """
    booked: dict[str, list] = {}
    for link in Event.volunteers.through.objects.select_related("event"):
        ev = link.event
        booked.setdefault(str(link.volunteer_id), []).append([ev.starts_at.isoformat(), ev.ends_at.isoformat(), ev.pk])
    return booked


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(EventType)
class EventTypeAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(HomePageImages)
class HomePageImagesAdmin(admin.ModelAdmin):
    """A single record: the sidebar link goes straight to its upload form."""

    fields = [("map", "map_preview"), ("schedule", "schedule_preview"), "updated"]
    readonly_fields = ["map_preview", "schedule_preview", "updated"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def changelist_view(self, request, extra_context=None):
        return redirect("admin:schedule_homepageimages_change", HomePageImages.load().pk)

    def preview(self, obj: HomePageImages, kind: str) -> str:
        # Via the same route the home page links to (no /media/ URL); ?v= skips a cached old image
        url = f"/images/{kind}?v={obj.updated:%Y%m%d%H%M%S}"
        note = "" if getattr(obj, kind) else "Showing the placeholder mockup."
        return format_html('<a href="{0}"><img src="{0}" alt="" style="max-width: 240px; max-height: 240px;"></a><p>{1}</p>',
                           url, note)

    @admin.display(description="current map")
    def map_preview(self, obj: HomePageImages) -> str:
        return self.preview(obj, "map")

    @admin.display(description="current schedule")
    def schedule_preview(self, obj: HomePageImages) -> str:
        return self.preview(obj, "schedule")


def time_widget() -> AdminTimeWidget:
    """12-hour time input: 2:00 PM (no leading zero). Parsing formats are in smc/formats/en/formats.py."""
    return AdminTimeWidget(format="%-I:%M %p")


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ["__str__", "start", "end"]
    list_editable = ["start", "end"]
    list_display_links = None
    formfield_overrides = {models.TimeField: {"widget": time_widget()}}
    fields = ["day", "part", "start", "end"]


class StaffingFilter(admin.SimpleListFilter):
    title = "staffing"
    parameter_name = "staffing"

    def lookups(self, request, model_admin):
        return [("under", "Understaffed"), ("full", "Fully staffed"), ("over", "Overstaffed")]

    def queryset(self, request, queryset):
        # staff_count is annotated in EventAdmin.get_queryset
        match self.value():
            case "under":
                return queryset.filter(staff_count__lt=F("needed"))
            case "full":
                return queryset.filter(staff_count=F("needed"))
            case "over":
                return queryset.filter(staff_count__gt=F("needed"))
        return queryset


class VolunteerChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj: Volunteer) -> str:
        shifts = getattr(obj, "shift_count", 0)
        return f"{obj.full_name} · {shifts} shift{'' if shifts == 1 else 's'}"


class EventAdminForm(forms.ModelForm):
    volunteers = VolunteerChoiceField(
        queryset=Volunteer.objects.annotate(shift_count=Count("events")).prefetch_related("slots"),
        required=False,
        # Plain multi-select (not filter_horizontal) so the change_form script can filter its options
        widget=forms.SelectMultiple(attrs={"size": 15}),
        help_text="Volunteers already on an overlapping event aren't listed. "
                  "Hold Ctrl (Cmd on a Mac) to select more than one.",
    )

    class Meta:
        model = Event
        fields = ["name", "type", "day", "start", "end", "location", "needed", "volunteers", "description", "details"]
        # 2:00 PM rather than 14:00:00
        widgets = {"start": time_widget(), "end": time_widget()}

    def clean(self):
        cleaned = super().clean()
        times = [cleaned.get(f) for f in ("day", "start", "end", "location")]
        volunteers = cleaned.get("volunteers")
        if volunteers and None not in times:
            # The instance isn't updated until after clean(), so check the times as submitted
            day, start, end, location = times
            event = Event(pk=self.instance.pk, name=cleaned.get("name") or "", day=day, start=start, end=end, location=location)
            if problems := assignment_problems(event, volunteers):
                raise ValidationError(problems)
        return cleaned


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    form = EventAdminForm
    list_display = ["name", "when", "location", "type", "staffing"]
    list_select_related = ["type", "location"]
    list_filter = [StaffingFilter, "day", "type", "location"]
    search_fields = ["name", "description", "location__name", "volunteers__first", "volunteers__last"]
    list_per_page = 75
    save_as = True
    actions = ["print_roster", "export_csv"]
    fieldsets = [
        (None, {"fields": [("name", "type"), ("day", "start", "end"), "location"]}),
        ("Volunteers", {"fields": ["needed", "volunteers"]}),
        ("Details shown to volunteers", {"fields": ["description", "details"]}),
    ]
    # Adds the Board/Roster links and the script that narrows the volunteer list
    change_list_template = "admin/schedule/event/change_list.html"
    change_form_template = "admin/schedule/event/change_form.html"

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(staff_count=Count("volunteers", distinct=True))

    @admin.display(ordering=("day", "start"))
    def when(self, obj: Event) -> str:
        return obj.when

    @admin.display(ordering="staff_count")
    def staffing(self, obj: Event) -> str:
        return staffing_badge(obj.staff_count, obj.needed)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = {**(extra_context or {}), "volunteer_bookings": volunteer_bookings()}
        return super().changeform_view(request, object_id, form_url, extra_context)

    # ---- Rosters and export ----

    @admin.action(description="Print roster for selected events")
    def print_roster(self, request, queryset):
        ids = ",".join(str(pk) for pk in queryset.values_list("pk", flat=True))
        return redirect(f"{reverse('admin:schedule_event_roster')}?ids={ids}")

    @admin.action(description="Export selected events to CSV (includes contact details)")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="smc-assignments.csv"'
        writer = csv.writer(response)
        writer.writerow(["Day", "Start", "End", "Event", "Type", "Location", "Needed", "Staffed",
                         "First name", "Last name", "Email", "Phone"])
        events = queryset.select_related("type", "location").prefetch_related("volunteers").order_by("day", "start")
        for ev in events:
            row = [ev.day.isoformat(), format_time(ev.start), format_time(ev.end), ev.name,
                   ev.type.name if ev.type else "", ev.location.name, ev.needed, ev.volunteers.count()]
            people = list(ev.volunteers.all())
            # One row per assignment; an event with nobody on it still gets a row
            for v in people or [None]:
                writer.writerow(row + ([v.first, v.last, v.email, v.phone] if v else ["", "", "", ""]))
        return response

    # ---- Extra admin pages: board and roster ----

    def get_urls(self):
        return [
            path("board/", self.admin_site.admin_view(self.board_view), name="schedule_event_board"),
            path("roster/", self.admin_site.admin_view(self.roster_view), name="schedule_event_roster"),
            *super().get_urls(),
        ]

    def page_context(self, request, title: str) -> dict:
        return {**self.admin_site.each_context(request), "opts": self.model._meta, "title": title}

    def roster_view(self, request):
        events = (
            Event.objects.select_related("type", "location")
            .prefetch_related(Prefetch("volunteers", queryset=Volunteer.objects.order_by("last", "first")))
            .order_by("day", "start", "name")
        )
        if "ids" in request.GET:
            # Present but empty still filters (to nothing), rather than falling through to every event
            events = events.filter(pk__in=[int(i) for i in request.GET["ids"].split(",") if i.isdigit()])
        if day := request.GET.get("day"):
            events = events.filter(day=date.fromisoformat(day))
        if location := request.GET.get("location"):
            events = events.filter(location_id=location)
        days: dict[date, list[Event]] = {}
        for ev in events:
            days.setdefault(ev.day, []).append(ev)
        context = {
            **self.page_context(request, "Roster"),
            "days": [(format_day(d), evs) for d, evs in days.items()],
        }
        return TemplateResponse(request, "admin/schedule/event/roster.html", context)

    def board_view(self, request):
        events = list(
            Event.objects.select_related("type", "location")
            .prefetch_related("volunteers")
            .annotate(staff_count=Count("volunteers", distinct=True))
            .order_by("day", "start")
        )
        # Time axis: the earliest start to the latest end across all days (past midnight allowed)
        def hours_from_midnight(ev: Event, at: datetime) -> float:
            return (at - datetime.combine(ev.day, datetime.min.time())) / timedelta(hours=1)

        first_hour = int(min((hours_from_midnight(e, e.starts_at) for e in events), default=8))
        last_hour = -int(-max((hours_from_midnight(e, e.ends_at) for e in events), default=22))
        hour_px = 64

        columns = []
        for day in EVENT_DAYS:
            day_events = [e for e in events if e.day == day]
            # Greedy lanes so overlapping events sit side by side
            lane_ends: list[datetime] = []
            blocks = []
            for ev in day_events:
                lane = next((i for i, end in enumerate(lane_ends) if end <= ev.starts_at), len(lane_ends))
                if lane == len(lane_ends):
                    lane_ends.append(ev.ends_at)
                else:
                    lane_ends[lane] = ev.ends_at
                blocks.append({
                    "event": ev,
                    "lane": lane,
                    "top": (hours_from_midnight(ev, ev.starts_at) - first_hour) * hour_px,
                    "height": max(ev.hours * hour_px - 4, 28),
                    "staffing": staffing_badge(ev.staff_count, ev.needed),
                    "status": "under" if ev.staff_count < ev.needed else "over" if ev.staff_count > ev.needed else "full",
                    "people": ", ".join(v.full_name for v in ev.volunteers.all()) or "Nobody assigned yet",
                })
            lanes = max(len(lane_ends), 1)
            for b in blocks:
                b["left"] = 100 * b["lane"] / lanes
                b["width"] = 100 / lanes
            columns.append({"day": day, "label": format_day(day), "blocks": blocks,
                            "needed": sum(e.needed for e in day_events),
                            "staffed": sum(e.staff_count for e in day_events)})

        hours = [
            {"label": format_time(datetime.min.replace(hour=h % 24).time()), "top": (h - first_hour) * hour_px}
            for h in range(first_hour, last_hour + 1)
        ]
        context = {
            **self.page_context(request, "Schedule board"),
            "columns": columns,
            "hours": hours,
            "board_height": (last_hour - first_hour) * hour_px,
            "understaffed": sum(1 for e in events if e.staff_count < e.needed),
        }
        return TemplateResponse(request, "admin/schedule/event/board.html", context)


class ShiftsFilter(admin.SimpleListFilter):
    title = "shifts"
    parameter_name = "shifts"

    def lookups(self, request, model_admin):
        return [("none", "No shifts yet"), ("some", "Has shifts")]

    def queryset(self, request, queryset):
        # shift_count is annotated in VolunteerAdmin.get_queryset
        match self.value():
            case "none":
                return queryset.filter(shift_count=0)
            case "some":
                return queryset.filter(shift_count__gt=0)
        return queryset


class AvailableOnFilter(admin.SimpleListFilter):
    title = "available on"
    parameter_name = "available_on"

    def lookups(self, request, model_admin):
        # Each whole day, then each slot
        days = [(d.isoformat(), f"{format_day(d)} (any time)") for d in EVENT_DAYS]
        return days + [(f"slot-{s.pk}", str(s)) for s in TimeSlot.objects.all()]

    def queryset(self, request, queryset):
        match self.value():
            case None:
                return queryset
            case str(value) if value.startswith("slot-"):
                return queryset.filter(slots=value.removeprefix("slot-")).distinct()
            case value:
                return queryset.filter(slots__day=date.fromisoformat(value)).distinct()


class VolunteerAdminForm(forms.ModelForm):
    class Meta:
        model = Volunteer
        fields = "__all__"
        widgets = {"slots": forms.CheckboxSelectMultiple}


@admin.register(Volunteer)
class VolunteerAdmin(ImportMixin, admin.ModelAdmin):
    form = VolunteerAdminForm
    # Import only: the registration export (see schedule/resources.py). Event CSV export covers contact lists.
    resource_classes = [VolunteerResource]
    import_formats = [RegistrantsXLSX]
    list_display = ["first", "last", "availability", "shift_count", "total_hours"]
    list_filter = [ShiftsFilter, AvailableOnFilter, "availability_unsure", "volunteered_before"]
    search_fields = ["first", "last", "email", "phone"]
    list_per_page = 50
    readonly_fields = ["shifts", "registered_at"]
    fieldsets = [
        (None, {"fields": [("first", "last"), ("email", "phone"), "text_ok"]}),
        ("Availability", {"fields": ["slots", "availability_unsure", "workload_preference"]}),
        ("Scheduling notes", {"classes": ["collapse"], "fields": [
            "physical_limitations", "previous_role_preferences", "additional_info", "comments",
        ]}),
        ("Background", {"classes": ["collapse"], "fields": [
            ("volunteered_before", "tech_comfortable"), "relationship", "invited_by", "registered_at",
        ]}),
        ("Demographics & address", {"classes": ["collapse"], "fields": [
            ("gender", "age_range"), ("street1", "street2"), ("city", "state", "postal_code"), "country",
        ]}),
        ("Shifts", {"fields": ["shifts"]}),
    ]

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .annotate(shift_count=Count("events", distinct=True))
            .prefetch_related(Prefetch("events", queryset=Event.objects.select_related("location")), "slots")
        )

    @admin.display(description="shifts", ordering="shift_count")
    def shift_count(self, obj: Volunteer) -> int:
        return obj.shift_count

    @admin.display(description="hours")
    def total_hours(self, obj: Volunteer) -> str:
        return f"{sum(ev.hours for ev in obj.events.all()):g}"

    @admin.display(description="shifts")
    def shifts(self, obj: Volunteer):
        # In time order (Event.Meta.ordering), each linking to its event
        events = list(obj.events.all())
        if not events:
            return "No shifts yet."
        rows = format_html_join(
            "", '<li><a href="{}"><strong>{}</strong></a> · {} @ {}</li>',
            ((reverse("admin:schedule_event_change", args=[ev.pk]), ev.name, ev.when, ev.location) for ev in events),
        )
        hours = f"{sum(ev.hours for ev in events):g}"
        return format_html('<ul class="shift-list">{}</ul><p>{} hours in total.</p>', rows, hours)


admin.site.site_header = admin.site.site_title = "SMC Admin"
admin.site.index_title = "Volunteer scheduling"
