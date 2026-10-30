# SMC 2027 Volunteer Scheduling

Volunteer scheduling for SMC 2027 (Jan 2–5, 2027).

- **Volunteers** look up their own schedule on a simple mobile-friendly page.
- **Organizers** add volunteers and build the schedule in an admin site. It includes a day-by-day board, staffing counts, printable rosters and CSV export, and checks that stop anyone being double-booked or scheduled outside their availability.

Built with [Django](https://www.djangoproject.com/) served by [Django-Bolt](https://github.com/FarhanAliRaza/django-bolt), with a local SQLite database.

## Quick start

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                    # install dependencies
cp .env.example .env                       # or create .env by hand (see Configuration); then fill it in
uv run python manage.py migrate            # create the database (data/db.sqlite3)
uv run python manage.py ensure_admin       # create the admin login from .env
DEBUG=true uv run python manage.py runbolt --dev --host 127.0.0.1
```

Then open:

| Page | URL |
|---|---|
| Volunteer schedule lookup | http://127.0.0.1:8000/ |
| Admin | http://127.0.0.1:8000/admin/ |

`DEBUG=true` is needed to log in to the admin over plain `http://`. `--dev` reloads the server when files change. Never use `DEBUG=true` in production.

### Mock data

To try things out with made-up events and volunteers:

```bash
uv run python manage.py seed_mock            # refuses if the database already has data
uv run python manage.py seed_mock --reset    # deletes ALL events, volunteers, and locations first
```

Never run `--reset` against a database with real volunteers.

## Configuration

Settings are read from a `.env` file in the project root; real environment variables take precedence. Don't commit `.env`.

```ini
# Required
username=<admin username>
password=<admin password>          # run `manage.py ensure_admin` after changing either
secret_key=<long random value>     # Django SECRET_KEY; changing it signs everyone out

# Optional
time_zone=America/Chicago          # default; event times are stored as local clock times
db_path=data/db.sqlite3            # default
allowed_hosts=["smc.example.com","localhost","127.0.0.1"]
csrf_trusted_origins=["https://smc.example.com"]

# Docker / Caddy only
DOMAIN=smc.example.com
ACME_EMAIL=you@example.com
```

Generate random values with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Using the admin

The header links go to **Board**, **Events**, and **Volunteers**.

- **Events.** Each event has a day, start and end time, a location, how many volunteers it needs, and who is assigned.
  - The volunteer list on the event form only shows people who are free at that time, and it updates as you change the day or times.
  - Saving is blocked if anyone is outside their availability or already on an overlapping event.
  - An end time at or before the start time means the event runs past midnight.
- **Staffing.** The events list shows each event's staffing as, for example, `3 / 8` (red = short, green = full, blue = over). Filter by **Understaffed** to see what still needs filling.
- **Board.** Every event laid out by day and time, colored by staffing. Click an event to edit it.
- **Rosters.** Use **Print roster** (all events, or one day from the board), or select events and choose the *Print roster* action. Each day prints on its own page. Rosters include phone numbers, so hand them only to event leads.
- **CSV export.** Select events and choose *Export selected events to CSV*. The file includes volunteers' email addresses and phone numbers.
- **Volunteers.** Add volunteers with *Add volunteer*, entering their contact details and the window they're available. The list shows each person's shift count and hours, with filters for *No shifts yet* and *Available on* a given day. A volunteer's page lists their shifts in time order.

## Customizing

- **Map and full-schedule images.** Replace `schedule/static/photos/map.jpeg` and `schedule.jpeg` (the committed ones are mockups). Keep the same file names.
- **Event dates.** Update `EVENT_FIRST_DAY` / `EVENT_LAST_DAY` in `schedule/models.py`, then run `makemigrations` and `migrate`.
- **Event types.** Manage these in the admin. The defaults are seeded by migration `0002`.
- **Brand.**
  - Colors are in `schedule/templates/schedule/theme.css`.
  - Source artwork is in `theme/`.
  - Web-sized logos and icons are in `schedule/static/brand/`.

## Deployment (Docker + Caddy)

```bash
docker compose up --build -d
```

- **app.** Builds the image. On start it applies migrations, syncs the admin login from `.env`, and serves on port 8000 inside the network. The database lives on the `app-data` volume.
- **caddy.** Serves `DOMAIN` over HTTPS with a free Let's Encrypt certificate that renews automatically, and redirects http to https. Certificates are kept on the `caddy-data` volume.

Before deploying:

1. Point the domain's DNS at the server, and open ports 80 and 443.
2. In `.env`, set `DOMAIN`, `ACME_EMAIL`, `allowed_hosts`, and `csrf_trusted_origins`.
3. Make sure `DEBUG` is not set.

If the site will run on a company-managed domain, check with IT whether Let's Encrypt certificates are allowed. To use your own certificate instead, replace the automatic setup in `Caddyfile` with `tls /path/to/fullchain.pem /path/to/privkey.pem`.

**Backups.** The whole database is one file. Copy it out of the volume regularly, for example:

```bash
docker compose cp app:/app/data/db.sqlite3 ./backup-$(date +%F).sqlite3
```

## Project structure

```
manage.py
smc/                    Django project: settings, .env loading (env.py), URLs
schedule/               the app
  models.py             Event, Volunteer, Location, EventType + scheduling rules
  api.py                public page and JSON (Bolt routes): /, /api/...
  admin.py              admin setup, board, roster, CSV export
  signals.py            backstop checks for changes made outside forms
  management/commands/  ensure_admin, seed_mock
  templates/            viewer, admin overrides, shared theme.css
  static/               brand images, map/schedule images
theme/                  source brand artwork (not deployed)
Caddyfile, compose.yaml, Dockerfile
```

See `CLAUDE.md` for architecture notes.
