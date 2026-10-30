from django.apps import AppConfig


class ScheduleConfig(AppConfig):
    name = "schedule"
    verbose_name = "SMC"

    def ready(self) -> None:
        from schedule import signals  # noqa: F401  registers the availability check
