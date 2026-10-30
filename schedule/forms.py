from django import forms

from schedule.models import Volunteer


class SignupForm(forms.ModelForm):
    class Meta:
        model = Volunteer
        fields = ["first", "last", "email", "phone", "availability_start", "start_time", "availability_end", "end_time"]
        widgets = {
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        for name in ("first", "last", "email", "phone"):
            if isinstance(cleaned.get(name), str):
                cleaned[name] = cleaned[name].strip()
        return cleaned
