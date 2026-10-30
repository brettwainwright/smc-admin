from django.contrib import admin
from django.urls import path

# Public pages are BoltAPI routes in schedule/api.py; runbolt mounts Django (and so admin) at /admin
urlpatterns = [
    path("admin/", admin.site.urls),
]
