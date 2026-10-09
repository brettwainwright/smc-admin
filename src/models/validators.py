from wtforms.validators import DataRequired, Length, Regexp

def email_validators():
    return [
        DataRequired(),
        Length(max=254),
        Regexp(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", message="Enter a valid email address."),
    ]


def phone_validators():
    return [
        DataRequired(),
        Length(max=25),
        Regexp(r"^\+?[\d\s().-]{7,}$", message="Enter a valid phone number."),
    ]