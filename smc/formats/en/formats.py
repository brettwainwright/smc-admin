# 12-hour times in the admin (2:00 PM rather than 14:00:00). Formats not set here fall back to
# Django's en locale. Enabled by FORMAT_MODULE_PATH in smc/settings.py.

TIME_FORMAT = "g:i A"  # 2:00 PM (read-only and list display)

# Accepted when typing a time; the first is also what the admin's clock picker and "Now" insert.
# strptime's %p ignores case and %I takes one or two digits, so "2:00 pm" and "02:00 PM" both work.
TIME_INPUT_FORMATS = [
    "%I:%M %p",  # 2:00 PM
    "%I:%M%p",  # 2:00pm
    "%I %p",  # 2 pm
    "%I%p",  # 2pm
    "%H:%M",  # 14:00 is still accepted
    "%H:%M:%S",
]
