from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from smc.env import settings


class Command(BaseCommand):
    help = "Create or update the admin superuser from the username/password settings in .env"

    def handle(self, *args, **options):
        user, created = get_user_model().objects.get_or_create(username=settings.username)
        user.is_staff = user.is_superuser = True
        user.set_password(settings.password)
        user.save()
        self.stdout.write(f"{'Created' if created else 'Updated'} admin user.")
