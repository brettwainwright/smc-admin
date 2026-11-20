from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

validate_email = RegexValidator(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", message="Enter a valid email address.")
validate_phone = RegexValidator(r"^\+?[\d\s().-]{7,}$", message="Enter a valid phone number.")

MAX_IMAGE_MB = 10


def validate_image_size(file) -> None:
    if file.size > MAX_IMAGE_MB * 1024 * 1024:
        raise ValidationError(f"Images can be at most {MAX_IMAGE_MB} MB.")
