# +15 Partner Portal

A CRUD web application for managing the businesses ("partners") located in
Calgary's **+15 skywalk** buildings and the promotions they advertise to people
navigating the network.

Built for **BANA 5140 — Data Management** using **Python, Flask, and SQLite3**.

---

## What it does

The +15 skywalk connects 100+ downtown buildings, and dozens of businesses sit
along it. This portal is the back-office tool a +15 management organization (e.g.
the Calgary Downtown Association) would use to keep partner listings and
promotions accurate. Staff can:

- **Create** new partner businesses and their promotions
- **Read** partners in a searchable, filterable list and on detail pages
- **Update** partner records and promotions through pre-filled forms
- **Delete** partners (cascading to their promotions, hours, and lease) and
  individual promotions, each behind a confirmation step

It also includes a dashboard with simple reports, three-tier login
(admin / steward / read-only viewer), server-side validation, and a buildings
reference view.

---

## Tech stack

| Layer     | Choice                                   |
|-----------|------------------------------------------|
| Language  | Python 3                                 |
| Web        | Flask (routing + Jinja2 templates)      |
| Database  | SQLite3 via Python's built-in `sqlite3` |
| Auth      | Werkzeug password hashing               |
| Styling   | Plain CSS (no framework)                |

---

## Setup

> Requires Python 3.9 or newer.

### 1. Create a virtual environment and install dependencies

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Initialize the database

This builds `plus15_portal.db` from `schema.sql` and loads the seed data: real
+15 buildings, **51 real restaurants** currently operating in the network (from
`seed_restaurants.csv`, with their real addresses, descriptions, and hours), and
a small set of sample promotions and leases for demonstration.

```bash
python init_db.py
```

You should see a row count for each of the seven tables.

### 3. Run the application

```bash
python app.py
```

Then open **http://127.0.0.1:5000** in a browser.

*(Shortcut: `./run.sh` does steps 2 and 3 together on macOS/Linux.)*

---

## Demo accounts

| Username | Password     | Role    | Can edit? |
|----------|--------------|---------|-----------|
| `admin`  | `admin123`   | admin   | Yes       |
| `jchau`  | `steward123` | steward | Yes       |
| `viewer` | `viewer123`  | viewer  | No (read-only) |

---

## Using the app

1. **Sign in** with one of the accounts above.
2. **Dashboard** — summary counts, partners-by-category report, featured live promotions.
3. **Partners** — search by name/description, filter by category or status.
   - **Add partner** (Create) — top-right button.
   - Click a partner to open its **detail** page (Read).
   - **Edit** (Update) from the list or detail page.
   - **Delete** (Delete) from the detail page, with a confirmation prompt.
4. **Promotions** — managed from a partner's detail page (Create / Update / Delete).
5. **Buildings** — read-only reference list with a partner count per building.

---

## Project structure

```
plus15_portal/
├── app.py                 # Flask application: routes + all CRUD logic
├── schema.sql             # SQLite schema: 7 tables, keys, constraints, indexes
├── init_db.py             # Creates the DB and loads seed data
├── seed_restaurants.csv   # Real +15 restaurant directory used as partner seed data
├── requirements.txt       # Python dependencies
├── run.sh                 # Convenience launcher (init + run)
├── plus15_portal.db       # SQLite database (created by init_db.py)
├── templates/             # Jinja2 templates
│   ├── base.html          # Shared layout (nav, flash messages)
│   ├── login.html
│   ├── dashboard.html
│   ├── partners.html      # List + search/filter (Read)
│   ├── partner_detail.html# Single partner + related records (Read/Delete)
│   ├── partner_form.html  # Shared Create/Update form
│   ├── promotion_form.html# Promotion Create/Update form
│   ├── buildings.html
│   └── 404.html
└── static/
    └── style.css
```

---

## Running it online (deployment)

The project is configured for free hosting on [Render](https://render.com):

- `requirements.txt` includes `gunicorn` (the production web server).
- `wsgi.py` is the production entry point; it builds the SQLite database on
  first boot if it does not yet exist, then serves the app.
- `Procfile` and `render.yaml` tell the host how to start the service
  (`gunicorn wsgi:app`).

To deploy: push this repository to GitHub, create a new Web Service on Render
pointed at the repo, and Render reads `render.yaml` automatically. The result is
a public URL serving the live application.

## Notes for grading

- The database file is included so the app runs immediately, but you can rebuild
  it any time with `python init_db.py` (it resets to the same known state).
- Foreign keys are enforced on every connection (`PRAGMA foreign_keys = ON`),
  so deleting a partner cascades to its child records and invalid references are
  rejected.
- No virtual environment folder is included in the submission; recreate it with
  the steps above.
