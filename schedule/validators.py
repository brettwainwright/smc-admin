from django.core.validators import RegexValidator

validate_email = RegexValidator(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", message="Enter a valid email address.")
validate_phone = RegexValidator(r"^\+?[\d\s().-]{7,}$", message="Enter a valid phone number.")
