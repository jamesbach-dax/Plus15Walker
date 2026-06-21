"""
init_db.py — create the SQLite database from schema.sql and load seed data.

Run once before first use:   python init_db.py

This script is idempotent: it drops and recreates plus15_portal.db each time,
so the instructor always gets a known, working dataset.

Seed data provenance
---------------------
* building : real +15-connected buildings (City of Calgary open "Plus 15" data).
* partner  : REAL restaurants currently operating in the +15 network, loaded
             from seed_restaurants.csv (compiled by the project author from
             building directories). Names, addresses, descriptions and hours
             are real; missing values in the source are stored as NULL.
* category : every CSV partner is a food/beverage business, so it is assigned
             the "Food & Beverage" category; the other categories remain in the
             controlled vocabulary for use as the portal grows.
* promotion / lease : SYNTHETIC. Promotions and lease terms are not public
             information, so a small set of realistic sample records is attached
             to a few partners purely to demonstrate those CRUD features.
"""

import os
import csv
import sqlite3
from datetime import date, timedelta
from werkzeug.security import generate_password_hash

BASE = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE, "plus15_portal.db")
SCHEMA_PATH = os.path.join(BASE, "schema.sql")
CSV_PATH = os.path.join(BASE, "seed_restaurants.csv")

NA = {"", "not provided", "n/a", "na"}   # tokens treated as "missing" -> NULL


def get_connection():
    """Return a SQLite connection with foreign keys enforced and row access by name."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")   # SQLite needs this per connection
    conn.row_factory = sqlite3.Row
    return conn


def clean(value):
    """Return a trimmed value, or None if it is blank / a 'not provided' token."""
    if value is None:
        return None
    v = value.strip()
    return None if v.lower() in NA else v


# Real +15-connected buildings from City of Calgary open data, plus any building
# that appears in the restaurant CSV (so every partner has a valid building FK).
BUILDINGS = [
    ("Bankers Hall", "SW", 51.04679, -114.06820),
    ("The Core (3rd St SW)", "SW", 51.04618, -114.07037),
    ("Suncor Energy Centre", "SW", 51.04706, -114.06650),
    ("Bow Valley Square", "SW", 51.04824, -114.06579),
    ("First Canadian Centre", "SW", 51.04760, -114.07010),
    ("Eighth Avenue Place", "SW", 51.04640, -114.07150),
    ("Fifth Avenue Place", "SW", 51.04760, -114.06880),
    ("Gulf Canada Square", "SW", 51.04690, -114.07180),
    ("Scotia Centre", "SW", 51.04610, -114.06760),
    ("TD Square", "SW", 51.04640, -114.06860),
    ("Jamieson Place", "SW", 51.04790, -114.07240),
    ("Livingston Place", "SW", 51.04850, -114.07020),
    ("Calgary Place", "SW", 51.04720, -114.06560),
    ("Devon Tower", "SW", 51.04650, -114.06650),
    ("Telus Convention Centre", "SE", 51.04540, -114.06280),
    ("The Bow", "SE", 51.04560, -114.06330),
    ("City Centre", "SW", 51.04680, -114.06480),
    # Buildings that appear only in the restaurant directory:
    ("707 Fifth Street SW", "SW", 51.04760, -114.07260),
    ("Nexen Building", "SW", 51.04680, -114.07330),
    ("Stephen Avenue Place", "SW", 51.04560, -114.06640),
    ("The Ampersand", "SW", 51.04610, -114.07020),
    ("TransCanada Tower", "SW", 51.04700, -114.06900),
    ("Watermark Tower", "SW", 51.04590, -114.06770),
]

CATEGORIES = [
    ("Food & Beverage", "Restaurants, cafes, quick-serve and coffee shops"),
    ("Retail", "Clothing, gifts, electronics and general merchandise"),
    ("Health & Wellness", "Pharmacies, clinics, dental and fitness studios"),
    ("Professional Services", "Banks, legal, accounting and consulting offices"),
    ("Personal Services", "Salons, dry cleaning, repair and convenience"),
    ("Entertainment & Culture", "Galleries, venues and attractions"),
]
FOOD_CATEGORY = "Food & Beverage"

# Synthetic promotions attached by partner business_name (real promos are not public).
PROMOS = [
    ("Eighth Avenue Trattoria (E.A.T.)", "Weekday Lunch Special", "Hot plate plus salad bar for $16.", 0, -5, 30, 1),
    ("Cucina Market Bistro", "Pasta Tuesday", "15% off all fresh pasta dishes every Tuesday.", 15, -2, 60, 1),
    ("Garbanzo's", "Lunch Bowl Deal", "Turmeric rice bowl plus pita for $13.99.", 10, -1, 21, 1),
    ("Analog Coffee", "Morning Rush 20% Off", "20% off any espresso drink before 9 AM.", 20, -3, 30, 1),
    ("Holy Grill", "Combo Friday", "Burger, fries and a drink combo at a set price.", 0, 0, 45, 0),
]

# Synthetic leases attached by partner business_name + building (commercial data is private).
LEASES = [
    ("Eighth Avenue Trattoria (E.A.T.)", "Eighth Avenue Place", -700, 1825, 8200.00, "active"),
    ("Cucina Market Bistro", "Eighth Avenue Place", -400, 1095, 6100.00, "active"),
    ("Garbanzo's", "Gulf Canada Square", -300, 1095, 3900.00, "active"),
    ("Holy Grill", "The Ampersand", -200, 730, 4500.00, "active"),
]

USERS = [
    ("admin", "Portal Administrator", "admin@plus15portal.ca", "admin", "admin123"),
    ("jchau", "James Chau", "james@plus15portal.ca", "steward", "steward123"),
    ("viewer", "Read Only", "viewer@plus15portal.ca", "viewer", "viewer123"),
]


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = get_connection()
    cur = conn.cursor()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        cur.executescript(f.read())

    for name, quad, lat, lng in BUILDINGS:
        cur.execute(
            "INSERT INTO building (name, quadrant, latitude, longitude) VALUES (?,?,?,?)",
            (name, quad, lat, lng),
        )
    for name, desc in CATEGORIES:
        cur.execute("INSERT INTO category (name, description) VALUES (?,?)", (name, desc))

    building_id = {r["name"]: r["building_id"] for r in cur.execute("SELECT * FROM building")}
    food_id = cur.execute("SELECT category_id FROM category WHERE name=?", (FOOD_CATEGORY,)).fetchone()["category_id"]

    partner_id = {}
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bname = clean(row["business_name"])
            bldg = clean(row["building_name"])
            if not bname or not bldg:
                continue
            if bldg not in building_id:
                cur.execute("INSERT INTO building (name, quadrant) VALUES (?, 'SW')", (bldg,))
                building_id[bldg] = cur.lastrowid

            cur.execute(
                """INSERT INTO partner
                   (business_name, building_id, category_id, unit_number,
                    contact_name, contact_email, contact_phone, description, status)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (bname, building_id[bldg], food_id,
                 clean(row.get("address")),
                 None,
                 clean(row.get("email")),
                 clean(row.get("phone")),
                 clean(row.get("restaurant description")),
                 "active"),
            )
            pid = cur.lastrowid
            partner_id[(bname, bldg)] = pid

            ot = clean(row.get("open time"))
            ct = clean(row.get("close time"))
            for d in range(7):
                if d < 5 and ot and ct:
                    cur.execute(
                        """INSERT INTO opening_hours
                           (partner_id, day_of_week, open_time, close_time, is_closed)
                           VALUES (?,?,?,?,0)""",
                        (pid, d, ot, ct),
                    )
                else:
                    cur.execute(
                        """INSERT INTO opening_hours
                           (partner_id, day_of_week, open_time, close_time, is_closed)
                           VALUES (?,?,NULL,NULL,1)""",
                        (pid, d),
                    )

    today = date.today()
    name_to_pid = {}
    for (bn, bldg), pid in partner_id.items():
        name_to_pid.setdefault(bn, pid)
    for bn, title, details, disc, start_off, length, feat in PROMOS:
        pid = name_to_pid.get(bn)
        if pid is None:
            continue
        s = today + timedelta(days=start_off)
        e = s + timedelta(days=length)
        cur.execute(
            """INSERT INTO promotion
               (partner_id, title, details, discount_pct, start_date, end_date, is_featured)
               VALUES (?,?,?,?,?,?,?)""",
            (pid, title, details, disc, s.isoformat(), e.isoformat(), feat),
        )

    for bn, bldg, start_off, term, rent, status in LEASES:
        pid = partner_id.get((bn, bldg)) or name_to_pid.get(bn)
        if pid is None:
            continue
        s = today + timedelta(days=start_off)
        e = s + timedelta(days=term)
        cur.execute(
            """INSERT INTO lease (partner_id, start_date, end_date, monthly_rent, status)
               VALUES (?,?,?,?,?)""",
            (pid, s.isoformat(), e.isoformat(), rent, status),
        )

    for username, full, email, role, pw in USERS:
        cur.execute(
            """INSERT INTO portal_user (username, full_name, email, role, password_hash)
               VALUES (?,?,?,?,?)""",
            (username, full, email, role, generate_password_hash(pw)),
        )

    conn.commit()
    for tbl in ("building", "category", "partner", "opening_hours", "promotion", "lease", "portal_user"):
        n = cur.execute(f"SELECT COUNT(*) AS c FROM {tbl}").fetchone()["c"]
        print(f"  {tbl:14s}: {n} rows")
    conn.close()
    print(f"\nDatabase created at {DB_PATH}")


if __name__ == "__main__":
    main()
