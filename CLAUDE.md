# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A volunteer scheduling app for an event (SMC 2027) running on fixed days (`EVENT_FIRST_DAY`–`EVENT_LAST_DAY` in `schedule/models.py`). It is a Django project served by [Django-Bolt](https://github.com/FarhanAliRaza/django-bolt) (`manage.py runbolt`, a Rust HTTP server), with a local SQLite database. One process serves everything:

- `/` — plain HTML viewer (`schedule/templates/schedule/viewer.html`): a volunteer picks their name and vanilla JS fetches and renders their events.
- `/api/volunteers`, `/api/volunteers/{id}/events` — JSON for the viewer.
- `/signup` — volunteer registration form, gated by a `?signup_key=` query param.
- `/admin/` — Django admin, including a schedule **board** (`/admin/schedule/event/board/`) and a printable **roster** (`/admin/schedule/event/roster/`).
- `/static/` — admin assets, brand images (`schedule/static/brand/`), and the map/schedule images (`schedule/static/photos/`; the committed ones are labelled mockups).
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

- Required: `signup_key`, `username` / `password` (the admin superuser, applied by `ensure_admin`), `secret_key` (Django `SECRET_KEY`).
- Optional: `db_path` (default `data/db.sqlite3`), `debug`, `time_zone` (default `America/Chicago`), `allowed_hosts` and `csrf_trusted_origins` (JSON lists, e.g. `["smc.example.com"]`; must include the public domain in production or admin requests are rejected).
- `hide_input_in_errors=True` keeps validation errors from echoing `.env` values; keep it.
- For Docker/Caddy, `.env` also needs `DOMAIN` and `ACME_EMAIL` (read by compose, not by the app).

## Architecture notes

- **Bolt routes vs Django.** Public pages and JSON live in `schedule/api.py` as `BoltAPI` routes (autodiscovered by `runbolt`). `runbolt` auto-mounts Django's ASGI app for `/admin` (from `smc/urls.py`); there are no other Django URL patterns.
- **Bolt handlers are `async` and call the ORM via `sync_to_thread`.** Bolt only runs sync handlers in a thread when its static analysis sees ORM calls in the handler body, so ORM work done through helper functions raised `SynchronousOnlyOperation`. Follow the existing pattern. Form posts are parsed with `QueryDict(request.body)`; responses use `django_bolt.shortcuts.render`, `HTML`, `Redirect`.
- **Data model.** `Event` has `volunteers` (M2M to `Volunteer`, `related_name="events"`) and `needed` (head count). There is no separate schedule model; migrations 0003–0005 moved the old `Schedule` rows onto events. `Event.Meta.ordering` is day/start, so `volunteer.events` comes back in time order.
- **Overnight events.** An event whose `end <= start` runs past midnight (`Event.ends_at`). Use `starts_at`/`ends_at`/`overlaps()`/`hours` rather than comparing raw times.
- **Assignment rules** (availability window + no double-booking) live in `assignment_problems()` in `schedule/models.py` and are enforced in three places:
  - `EventAdminForm.clean` (`schedule/admin.py`) checks the submitted times against the submitted volunteers and shows errors on the form.
  - The `m2m_changed` signal in `schedule/signals.py` is the backstop for `event.volunteers.add()` / `volunteer.events.add()` outside forms.
  - `Volunteer.clean` plus a `pre_save` signal reject availability edits that would strand existing assignments.
  - Event time edits outside a form are intentionally *not* re-checked: admin saves the event before its new volunteer list, so a `pre_save` check would test new times against the old list.
- **Day ranges** are enforced by DB `CheckConstraint`s (`in_event_days()`) and by `choices=DAY_CHOICES` on the date fields, which drives the admin and signup selects. Changing the event dates means updating the constants and generating a migration.
- **Admin extras** (`schedule/admin.py`):
  - Board and roster are custom views added via `EventAdmin.get_urls`.
  - Print and CSV export are admin actions. The CSV and roster contain volunteer contact details.
  - Staffing badges use `staff_count`, annotated in `get_queryset`; `StaffingFilter` and the "staffing" column depend on that annotation.
  - The event form's volunteer `<select>` is a plain multi-select (not `filter_horizontal`) so `admin/schedule/event/change_form.html` can filter it client-side from `volunteer_bookings`.
- **Template overrides.** `schedule` is listed *before* `django.contrib.admin` in `INSTALLED_APPS` so `schedule/templates/admin/base_site.html` overrides the admin's. Use `{% comment %}` for multi-line template comments: `{# #}` is single-line only and otherwise renders as page text. Django 6 admin breadcrumbs are `<ol class="breadcrumbs"><li>…`.
- **Admin CSS specificity.** The admin underlines links with `a:not(#header a, #content-main.app-list a, …)`, which counts as (1,1,2). Overrides need more, e.g. `#content .board a.board-block`.

## Theming

- **Palette.** `schedule/templates/schedule/theme.css` holds the colors, sampled from the artwork in `theme/`: crimson `#9a0d2f`, red `#c03840`, coral `#f26f56`, navy `#285070`, teal `#4c7a8d`. It is `{% include %}`d inline by the viewer, the signup page, and `admin/base_site.html`.
- **Admin colors.** `admin/base_site.html` maps the palette onto Django admin's CSS variables, setting only brand/accent roles so the admin's light/dark modes still work. Colors that must differ in dark mode (staffing badges, `--smc-heading`) have explicit `data-theme="dark"` / `prefers-color-scheme` rules.
- **Coral is decorative only.** It's too light for white text, so buttons use the crimson→red gradient.
- **Brand images.** `theme/` holds the full-size source artwork (excluded from the Docker image). `schedule/static/brand/` holds trimmed, web-sized copies; regenerate them from `theme/` if the artwork changes.

## Deployment

- **Dockerfile.** Runs `collectstatic` at build time with placeholder settings. On start it runs `migrate`, `ensure_admin`, then `runbolt` on :8000. The DB lives at `/app/data/db.sqlite3` on the `app-data` volume.
- **compose.yaml.** Puts Caddy (`Caddyfile`) in front: automatic HTTPS for `$DOMAIN`, with certificates on the `caddy-data` volume (keep it, because Let's Encrypt rate-limits). Caddy sets `X-Forwarded-Proto`, which Django reads via `SECURE_PROXY_SSL_HEADER`.
