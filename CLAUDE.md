# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A volunteer scheduling app for an event (SMC 2027) running on fixed days (`EVENT_FIRST_DAY`–`EVENT_LAST_DAY` in `schedule/models.py`). It is a Django project served by [Django-Bolt](https://github.com/FarhanAliRaza/django-bolt) (`manage.py runbolt`, a Rust HTTP server), with a local SQLite database. One process serves everything:

- `/` — plain HTML viewer (`schedule/templates/schedule/viewer.html`): a volunteer picks their name and vanilla JS fetches and renders their events.
- `/api/volunteers`, `/api/volunteers/{id}/events` — JSON for the viewer.
- `/admin/` — Django admin, including a schedule **board** (`/admin/schedule/event/board/`) and a printable **roster** (`/admin/schedule/event/roster/`).
- `/static/` — admin assets, brand images (`schedule/static/brand/`), and the fallback map/schedule mockups (`schedule/static/photos/`).
- `/map`, `/schedule` — pages around the map/schedule image (`schedule/templates/schedule/image.html`), so the tab gets a title; `/images/map`, `/images/schedule` serve the image uploaded in the admin (**Home page images**), or redirect to the mockup until one is uploaded.
- `/health`, `/ready` — Bolt's health endpoints (`/ready` also checks the DB); Docker's healthcheck uses `/health`.

The README describes the original Streamlit starter template and is stale.

## Commands

```bash
uv sync                                                      # install deps
uv run python manage.py migrate                              # create/upgrade the SQLite DB (seeds event types)
uv run python manage.py ensure_admin                         # create/update the admin superuser from .env
DEBUG=true uv run python manage.py runbolt --dev --host 127.0.0.1   # dev server on :8000 with auto-reload
uv run python manage.py seed_mock [--reset]                  # fill the DB with made-up data (--reset wipes events/volunteers/locations first)
uv run python manage.py makemigrations schedule              # after changing models
docker compose up --build                                    # app + Caddy (automatic Let's Encrypt HTTPS)
```

Without `--dev`, templates are cached until the server restarts. Without `DEBUG=true`, session/CSRF cookies are HTTPS-only, so admin login fails over plain http://localhost.

There are no tests, linter, or formatter configured.

## Configuration

`smc/env.py` loads a pydantic-settings `Settings` from the project-root `.env` (env vars override, case-insensitive); `smc/settings.py` maps it onto Django settings. Import `settings` from `smc.env` for app config rather than reading env vars directly.

- Required (with minimum lengths, so blanks are rejected): `username` / `password` (the admin superuser, applied by `ensure_admin`), `secret_key` (Django `SECRET_KEY`).
- Optional: `db_path` (default `data/db.sqlite3`), `debug`, `time_zone` (default `America/Chicago`), `allowed_hosts` and `csrf_trusted_origins` (JSON lists, e.g. `["smc.example.com"]`; must include the public domain in production or admin requests are rejected).
- `hide_input_in_errors=True` keeps validation errors from echoing `.env` values; keep it.
- For Docker/Caddy, `.env` also needs `DOMAIN` and `ACME_EMAIL` (read by compose, not by the app).

## Architecture notes

- **Bolt routes vs Django.** The public page and JSON live in `schedule/api.py` as `BoltAPI` routes (autodiscovered by `runbolt`). `runbolt` auto-mounts Django's ASGI app for `/admin` (from `smc/urls.py`); there are no other Django URL patterns.
- **Bolt handlers are `async` and call the ORM via `sync_to_thread`.** Bolt only runs sync handlers in a thread when its static analysis sees ORM calls in the handler body, so ORM work done through helper functions raised `SynchronousOnlyOperation`. Follow the existing pattern. HTML responses use `django_bolt.shortcuts.render`. Volunteers are only created in the admin; there is no public sign-up.
- **Data model.** `Event` has `volunteers` (M2M to `Volunteer`, `related_name="events"`) and `needed` (head count). There is no separate schedule model; migrations 0003–0005 moved the old `Schedule` rows onto events. `Event.Meta.ordering` is day/start, so `volunteer.events` comes back in time order.
- **Availability is slots.** `TimeSlot` rows (day × morning/afternoon/evening, seeded by migration 0006, times editable in the admin) are linked to volunteers via `Volunteer.slots` (M2M). Slots are informational: they are **not** enforced on assignments, because event times needn't line up with slot times. `is_available_for(event)` (event overlaps a slot) is only used by `seed_mock` to make realistic data. `availability_unsure` records "not sure yet" from the registration form.
- **Overnight events.** An event whose `end <= start` runs past midnight (`Event.ends_at`). Use `starts_at`/`ends_at`/`overlaps()`/`hours` rather than comparing raw times.
- **Assignment rule** (no double-booking: a volunteer can't be on two overlapping events) lives in `assignment_problems()` in `schedule/models.py` and is enforced in two places:
  - `EventAdminForm.clean` (`schedule/admin.py`) checks the submitted times against the submitted volunteers and shows errors on the form.
  - The `m2m_changed` signal in `schedule/signals.py` is the backstop for `event.volunteers.add()` / `volunteer.events.add()` outside forms.
  - Intentionally *not* re-checked outside forms: event time edits (admin saves the event before its new volunteer list, so a `pre_save` check would test new times against the old list).
- **Registration import** (`schedule/resources.py`, admin: Volunteers → Import) uses django-import-export on the registration form's "Registrants" `.xlsx` export. `RegistrantsXLSX` skips the title rows above the "First Name" header; `HEADERS` maps columns by header prefix (some headers are whole questions); "Volunteer Times" tokens like `January 3rd - Afternoon` become slots, and an unrecognised token is a row error. Rows match existing volunteers on first + last + email (also a DB unique constraint), so re-importing updates rather than duplicates. The file holds registrants' personal details: never commit it or copy it into fixtures.
- **Home page images.** `HomePageImages` is a single row (`load()`); its admin has no add/delete and the changelist redirects to the upload form. Files go to `MEDIA_ROOT` (`data/media`, on the `app-data` volume in Docker), and replaced files are deleted on save. There is deliberately no `/media/` route: `/images/<kind>` serves them via Bolt's `FileResponse`, limited to `BOLT_ALLOWED_FILE_PATHS`. The `Caddyfile` body limit (12 MB) must stay above the 10 MB image cap.
- **Day ranges** are enforced by DB `CheckConstraint`s (`in_event_days()`) and by `choices=DAY_CHOICES` on the date fields, which drives the admin selects. Changing the event dates means updating the constants and generating a migration.
- **Admin extras** (`schedule/admin.py`):
  - Board and roster are custom views added via `EventAdmin.get_urls`.
  - Print and CSV export are admin actions. The CSV and roster contain volunteer contact details.
  - Staffing badges use `staff_count`, annotated in `get_queryset`; `StaffingFilter` and the "staffing" column depend on that annotation.
  - The event form's volunteer `<select>` is a plain multi-select (not `filter_horizontal`) so `admin/schedule/event/change_form.html` can hide double-booked volunteers client-side from `volunteer_bookings`.
- **Template overrides.** `schedule` is listed *before* `django.contrib.admin` in `INSTALLED_APPS` so `schedule/templates/admin/base_site.html` overrides the admin's. Use `{% comment %}` for multi-line template comments: `{# #}` is single-line only and otherwise renders as page text. Django 6 admin breadcrumbs are `<ol class="breadcrumbs"><li>…`.
- **Admin CSS specificity.** The admin underlines links with `a:not(#header a, #content-main.app-list a, …)`, which counts as (1,1,2). Overrides need more, e.g. `#content .board a.board-block`.

## Theming

- **Palette.** `schedule/templates/schedule/theme.css` holds the colors, sampled from the artwork in `theme/`: crimson `#9a0d2f`, red `#c03840`, coral `#f26f56`, navy `#285070`, teal `#4c7a8d`. It is `{% include %}`d inline by the viewer and `admin/base_site.html`.
- **Admin colors.** `admin/base_site.html` maps the palette onto Django admin's CSS variables, setting only brand/accent roles so the admin's light/dark modes still work. Colors that must differ in dark mode (staffing badges, `--smc-heading`) have explicit `data-theme="dark"` / `prefers-color-scheme` rules.
- **Coral is decorative only.** It's too light for white text, so buttons use the crimson→red gradient.
- **Brand images.** `theme/` holds the full-size source artwork (excluded from the Docker image). `schedule/static/brand/` holds trimmed, web-sized copies; regenerate them from `theme/` if the artwork changes.

## Deployment

- **Dockerfile.** Runs `collectstatic` at build time with placeholder settings. On start it runs `migrate`, `ensure_admin`, then `runbolt` on :8000. The DB lives at `/app/data/db.sqlite3` on the `app-data` volume.
- **compose.yaml.** Puts Caddy (`Caddyfile`) in front: automatic HTTPS for `$DOMAIN`, with certificates on the `caddy-data` volume (keep it, because Let's Encrypt rate-limits). Caddy sets `X-Forwarded-Proto`, which Django reads via `SECURE_PROXY_SSL_HEADER`.
