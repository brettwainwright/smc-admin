"""Import volunteers from the registration form's "Registrants" .xlsx export (admin: Volunteers → Import).

The export has a title row and a blank row above the headers, and some headers are whole question
texts, so headers are matched by their opening words (HEADERS). People are matched on first + last +
email, so re-importing an updated export updates them instead of adding duplicates.
"""

import re
from datetime import date

import tablib
from django.core.exceptions import ValidationError
from import_export import fields, resources, widgets
from import_export.formats.base_formats import XLSX

from schedule.models import EVENT_FIRST_DAY, TimeSlot, Volunteer

# Header prefix (case-insensitive) -> Volunteer field. Columns not listed (Group, Fees) are ignored.
HEADERS = [
    ("First Name", "first"),
    ("Last Name", "last"),
    ("Email", "email"),
    ("Mobile", "phone"),
    ("Do you give StuMo permission to text", "text_ok"),
    ("Volunteer Times", "slots"),
    ("Workload Preference", "workload_preference"),
    ("Please list any physical limitations", "physical_limitations"),
    ("Preferences from Previous SMCs", "previous_role_preferences"),
    ("Any additional information", "additional_info"),
    ("Comments", "comments"),
    ("Have you volunteered at SMC before", "volunteered_before"),
    ("Are you comfortable using technology", "tech_comfortable"),
    ("Which best describes you", "relationship"),
    ("Which StuMo staff person invited you", "invited_by"),
    ("Created Datetime", "registered_at"),
    ("Gender", "gender"),
    ("Age Range", "age_range"),
    ("Street 1", "street1"),
    ("Street 2", "street2"),
    ("City", "city"),
    ("State", "state"),
    ("Postal Code", "postal_code"),
    ("Country", "country"),
]
REQUIRED = {"first", "last", "email", "phone", "slots"}
NOT_SURE = "not sure"


class RegistrantsXLSX(XLSX):
    """The first sheet, with the rows above the "First Name" header row and any blank rows dropped."""

    def get_title(self):
        return "xlsx (Registrants export)"

    def create_dataset(self, in_stream):
        dataset = super().create_dataset(in_stream)
        rows = [dataset.headers, *dataset]
        start = next((i for i, row in enumerate(rows) if row and str(row[0] or "").strip() == "First Name"), 0)
        trimmed = tablib.Dataset(headers=rows[start])
        for row in rows[start + 1:]:
            if any(value not in (None, "") for value in row):
                trimmed.append(row)
        return trimmed


class YesNoWidget(widgets.BooleanWidget):
    def clean(self, value, row=None, **kwargs):
        match str(value or "").strip().lower():
            case "yes":
                return True
            case "no":
                return False
            case "":
                return None
        raise ValueError(f"Expected Yes or No, got {value!r}.")


class SlotsWidget(widgets.ManyToManyWidget):
    """'January 3rd - Afternoon, January 4th - Morning' -> those TimeSlots.

    The "I'm not sure my availability yet" option is skipped here (it sets availability_unsure);
    anything else unrecognised is an error, so a changed form option can't silently drop availability.
    """

    TOKEN = re.compile(r"^January (\d{1,2})(?:st|nd|rd|th)? - (\w+)$", re.I)

    def clean(self, value, row=None, **kwargs):
        slots = {(s.day, s.part): s for s in TimeSlot.objects.all()}
        chosen = []
        for token in filter(None, (t.strip() for t in str(value or "").split(","))):
            if NOT_SURE in token.lower():
                continue
            m = self.TOKEN.match(token)
            key = m and (date(EVENT_FIRST_DAY.year, 1, int(m[1])), m[2].lower())
            if key not in slots:
                raise ValueError(f"Unrecognised volunteer time {token!r}.")
            chosen.append(slots[key].pk)
        return TimeSlot.objects.filter(pk__in=chosen)


class VolunteerResource(resources.ModelResource):
    text_ok = fields.Field("text_ok", "text_ok", YesNoWidget())
    volunteered_before = fields.Field("volunteered_before", "volunteered_before", YesNoWidget())
    tech_comfortable = fields.Field("tech_comfortable", "tech_comfortable", YesNoWidget())
    slots = fields.Field("slots", "slots", SlotsWidget(TimeSlot))
    registered_at = fields.Field("registered_at", "registered_at", widgets.DateTimeWidget("%m/%d/%Y %I:%M:%S %p"))

    class Meta:
        model = Volunteer
        import_id_fields = ["first", "last", "email"]
        fields = [field for _, field in HEADERS] + ["availability_unsure"]
        clean_model_instances = True
        skip_unchanged = True
        report_skipped = True

    def before_import(self, dataset, **kwargs):
        renamed = []
        for header in dataset.headers:
            text = str(header or "").strip().lower()
            renamed.append(next((field for prefix, field in HEADERS if text.startswith(prefix.lower())), header))
        if missing := REQUIRED - set(renamed):
            raise ValueError(f"The file is missing the column(s) for: {', '.join(sorted(missing))}.")
        dataset.headers = renamed

    def before_import_row(self, row, **kwargs):
        for key, value in row.items():
            if isinstance(value, str):
                row[key] = value.strip()
        row["availability_unsure"] = NOT_SURE in str(row.get("slots") or "").lower()

    def save_m2m(self, instance, row, **kwargs):
        super().save_m2m(instance, row, **kwargs)
        # Updating someone's slots mustn't strand events they're already on
        if problems := instance.availability_problems():
            raise ValidationError(" ".join(problems))
