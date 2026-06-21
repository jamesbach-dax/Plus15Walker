"""
app.py — +15 Partner Portal (BANA 5140 Final Project)

A Flask + SQLite3 CRUD application that lets portal staff (data stewards) manage
the businesses ("partners") located in Calgary's +15 skywalk buildings and the
promotions those businesses run.

Architecture
------------
* Flask handles routing and renders Jinja2 templates in /templates.
* Python's built-in sqlite3 library is the only data layer (no ORM), so every
  SQL statement is visible and the CRUD operations are explicit.
* Each request opens a connection with PRAGMA foreign_keys = ON so that
  referential integrity (e.g. ON DELETE CASCADE) is actually enforced.

CRUD coverage
-------------
The primary entity exposed through full Create / Read / Update / Delete is
`partner`. Promotions (a child entity) also have full CRUD to demonstrate
managing related records across a foreign-key relationship. Reads include
search and category/status filtering.

Run:  python init_db.py   (once, to build the database)
      python app.py        (starts the dev server on http://127.0.0.1:5000)
"""

import os
import sqlite3
from functools import wraps
from datetime import date

from flask import (Flask, g, render_template, request, redirect,
                   url_for, flash, session, abort)
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = "bana5140-plus15-portal-demo-key"  # demo only
DB_PATH = os.path.join(os.path.dirname(__file__), "plus15_portal.db")

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    """Open one SQLite connection per request, stored on Flask's `g` object."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row            # rows behave like dicts
        g.db.execute("PRAGMA foreign_keys = ON;")  # enforce FK constraints
    return g.db


@app.teardown_appcontext
def close_db(exception):
    """Close the per-request connection when the request ends."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ---------------------------------------------------------------------------
# Optional authentication — a light login gate to demonstrate the feature.
# Viewers can read; stewards/admins can write. This is intentionally simple.
# ---------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def writer_required(f):
    """Block read-only 'viewer' accounts from create/update/delete routes."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") == "viewer":
            flash("Your account is read-only.", "danger")
            return redirect(request.referrer or url_for("list_partners"))
        return f(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_user():
    """Make the signed-in user available to every template."""
    return {"current_user": session.get("full_name"), "current_role": session.get("role")}


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM portal_user WHERE username = ?", (username,)
        ).fetchone()
        if user and user["password_hash"] and check_password_hash(user["password_hash"], password):
            session.update(user_id=user["user_id"], full_name=user["full_name"], role=user["role"])
            flash(f"Welcome, {user['full_name']}.", "success")
            return redirect(request.args.get("next") or url_for("list_partners"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Validation helper — returns a list of human-readable errors for a partner form
# ---------------------------------------------------------------------------
def validate_partner(form):
    errors = []
    if not form.get("business_name", "").strip():
        errors.append("Business name is required.")
    if not form.get("building_id"):
        errors.append("Please choose a building.")
    if not form.get("category_id"):
        errors.append("Please choose a category.")
    email = form.get("contact_email", "").strip()
    if email and "@" not in email:
        errors.append("Contact email does not look valid.")
    return errors


# ---------------------------------------------------------------------------
# READ — dashboard
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    db = get_db()
    stats = {
        "partners": db.execute("SELECT COUNT(*) c FROM partner").fetchone()["c"],
        "active": db.execute("SELECT COUNT(*) c FROM partner WHERE status='active'").fetchone()["c"],
        "buildings": db.execute("SELECT COUNT(*) c FROM building").fetchone()["c"],
        "promos": db.execute(
            "SELECT COUNT(*) c FROM promotion WHERE date('now') BETWEEN start_date AND end_date"
        ).fetchone()["c"],
    }
    # Partners per category — a small "basic report" supporting the business case
    by_category = db.execute(
        """SELECT c.name, COUNT(p.partner_id) AS n
           FROM category c LEFT JOIN partner p ON p.category_id = c.category_id
           GROUP BY c.category_id ORDER BY n DESC"""
    ).fetchall()
    # Featured live promotions
    featured = db.execute(
        """SELECT pr.title, pr.end_date, p.business_name
           FROM promotion pr JOIN partner p ON p.partner_id = pr.partner_id
           WHERE pr.is_featured = 1 AND date('now') BETWEEN pr.start_date AND pr.end_date
           ORDER BY pr.end_date LIMIT 6"""
    ).fetchall()
    return render_template("dashboard.html", stats=stats, by_category=by_category, featured=featured)


# ---------------------------------------------------------------------------
# READ — list partners with search + filter
# ---------------------------------------------------------------------------
@app.route("/partners")
@login_required
def list_partners():
    db = get_db()
    q = request.args.get("q", "").strip()
    cat = request.args.get("category", "")
    status = request.args.get("status", "")

    sql = """SELECT p.*, b.name AS building_name, c.name AS category_name
             FROM partner p
             JOIN building b ON b.building_id = p.building_id
             JOIN category c ON c.category_id = p.category_id
             WHERE 1=1"""
    params = []
    if q:
        sql += " AND (p.business_name LIKE ? OR p.description LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if cat:
        sql += " AND p.category_id = ?"
        params.append(cat)
    if status:
        sql += " AND p.status = ?"
        params.append(status)
    sql += " ORDER BY p.business_name"

    partners = db.execute(sql, params).fetchall()
    categories = db.execute("SELECT * FROM category ORDER BY name").fetchall()
    return render_template("partners.html", partners=partners, categories=categories,
                           q=q, cat=cat, status=status)


# ---------------------------------------------------------------------------
# READ — single partner detail (with related promotions, hours, lease)
# ---------------------------------------------------------------------------
@app.route("/partners/<int:partner_id>")
@login_required
def view_partner(partner_id):
    db = get_db()
    partner = db.execute(
        """SELECT p.*, b.name AS building_name, b.quadrant, c.name AS category_name
           FROM partner p
           JOIN building b ON b.building_id = p.building_id
           JOIN category c ON c.category_id = p.category_id
           WHERE p.partner_id = ?""", (partner_id,)
    ).fetchone()
    if partner is None:
        abort(404)
    promos = db.execute(
        "SELECT * FROM promotion WHERE partner_id = ? ORDER BY start_date DESC", (partner_id,)
    ).fetchall()
    hours = db.execute(
        "SELECT * FROM opening_hours WHERE partner_id = ? ORDER BY day_of_week", (partner_id,)
    ).fetchall()
    lease = db.execute(
        "SELECT * FROM lease WHERE partner_id = ? ORDER BY start_date DESC LIMIT 1", (partner_id,)
    ).fetchone()
    return render_template("partner_detail.html", partner=partner, promos=promos,
                           hours=hours, lease=lease, days=DAYS, today=date.today().isoformat())


# ---------------------------------------------------------------------------
# CREATE — new partner
# ---------------------------------------------------------------------------
@app.route("/partners/new", methods=["GET", "POST"])
@login_required
@writer_required
def create_partner():
    db = get_db()
    if request.method == "POST":
        errors = validate_partner(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            db.execute(
                """INSERT INTO partner
                   (business_name, building_id, category_id, unit_number,
                    contact_name, contact_email, contact_phone, description, status)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (request.form["business_name"].strip(),
                 request.form["building_id"], request.form["category_id"],
                 request.form.get("unit_number", "").strip(),
                 request.form.get("contact_name", "").strip(),
                 request.form.get("contact_email", "").strip(),
                 request.form.get("contact_phone", "").strip(),
                 request.form.get("description", "").strip(),
                 request.form.get("status", "active")),
            )
            db.commit()
            flash("Partner created.", "success")
            return redirect(url_for("list_partners"))

    buildings = db.execute("SELECT * FROM building ORDER BY name").fetchall()
    categories = db.execute("SELECT * FROM category ORDER BY name").fetchall()
    return render_template("partner_form.html", mode="create", partner=None,
                           buildings=buildings, categories=categories)


# ---------------------------------------------------------------------------
# UPDATE — edit partner (form pre-filled with current values)
# ---------------------------------------------------------------------------
@app.route("/partners/<int:partner_id>/edit", methods=["GET", "POST"])
@login_required
@writer_required
def edit_partner(partner_id):
    db = get_db()
    partner = db.execute("SELECT * FROM partner WHERE partner_id = ?", (partner_id,)).fetchone()
    if partner is None:
        abort(404)

    if request.method == "POST":
        errors = validate_partner(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            db.execute(
                """UPDATE partner SET
                   business_name=?, building_id=?, category_id=?, unit_number=?,
                   contact_name=?, contact_email=?, contact_phone=?, description=?, status=?
                   WHERE partner_id=?""",
                (request.form["business_name"].strip(),
                 request.form["building_id"], request.form["category_id"],
                 request.form.get("unit_number", "").strip(),
                 request.form.get("contact_name", "").strip(),
                 request.form.get("contact_email", "").strip(),
                 request.form.get("contact_phone", "").strip(),
                 request.form.get("description", "").strip(),
                 request.form.get("status", "active"),
                 partner_id),
            )
            db.commit()
            flash("Partner updated.", "success")
            return redirect(url_for("view_partner", partner_id=partner_id))

    buildings = db.execute("SELECT * FROM building ORDER BY name").fetchall()
    categories = db.execute("SELECT * FROM category ORDER BY name").fetchall()
    return render_template("partner_form.html", mode="edit", partner=partner,
                           buildings=buildings, categories=categories)


# ---------------------------------------------------------------------------
# DELETE — remove partner (POST only, after a confirmation page)
# ON DELETE CASCADE removes the partner's promotions, hours and leases too.
# ---------------------------------------------------------------------------
@app.route("/partners/<int:partner_id>/delete", methods=["POST"])
@login_required
@writer_required
def delete_partner(partner_id):
    db = get_db()
    partner = db.execute("SELECT * FROM partner WHERE partner_id = ?", (partner_id,)).fetchone()
    if partner is None:
        abort(404)
    db.execute("DELETE FROM partner WHERE partner_id = ?", (partner_id,))
    db.commit()
    flash(f"Deleted '{partner['business_name']}' and its related records.", "success")
    return redirect(url_for("list_partners"))


# ---------------------------------------------------------------------------
# Promotions CRUD (child entity of partner) — demonstrates managing related
# records across a foreign key.
# ---------------------------------------------------------------------------
@app.route("/partners/<int:partner_id>/promotions/new", methods=["GET", "POST"])
@login_required
@writer_required
def create_promotion(partner_id):
    db = get_db()
    partner = db.execute("SELECT * FROM partner WHERE partner_id = ?", (partner_id,)).fetchone()
    if partner is None:
        abort(404)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        s = request.form.get("start_date", "")
        e = request.form.get("end_date", "")
        errs = []
        if not title:
            errs.append("Promotion title is required.")
        if not s or not e:
            errs.append("Start and end dates are required.")
        elif e < s:
            errs.append("End date cannot be before start date.")
        if errs:
            for x in errs:
                flash(x, "danger")
        else:
            db.execute(
                """INSERT INTO promotion
                   (partner_id, title, details, discount_pct, start_date, end_date, is_featured)
                   VALUES (?,?,?,?,?,?,?)""",
                (partner_id, title, request.form.get("details", "").strip(),
                 request.form.get("discount_pct") or None, s, e,
                 1 if request.form.get("is_featured") else 0),
            )
            db.commit()
            flash("Promotion added.", "success")
            return redirect(url_for("view_partner", partner_id=partner_id))
    return render_template("promotion_form.html", mode="create", partner=partner, promo=None)


@app.route("/promotions/<int:promotion_id>/edit", methods=["GET", "POST"])
@login_required
@writer_required
def edit_promotion(promotion_id):
    db = get_db()
    promo = db.execute("SELECT * FROM promotion WHERE promotion_id = ?", (promotion_id,)).fetchone()
    if promo is None:
        abort(404)
    partner = db.execute("SELECT * FROM partner WHERE partner_id = ?", (promo["partner_id"],)).fetchone()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        s = request.form.get("start_date", "")
        e = request.form.get("end_date", "")
        if not title or not s or not e or e < s:
            flash("Please provide a title and a valid date range.", "danger")
        else:
            db.execute(
                """UPDATE promotion SET title=?, details=?, discount_pct=?,
                   start_date=?, end_date=?, is_featured=? WHERE promotion_id=?""",
                (title, request.form.get("details", "").strip(),
                 request.form.get("discount_pct") or None, s, e,
                 1 if request.form.get("is_featured") else 0, promotion_id),
            )
            db.commit()
            flash("Promotion updated.", "success")
            return redirect(url_for("view_partner", partner_id=promo["partner_id"]))
    return render_template("promotion_form.html", mode="edit", partner=partner, promo=promo)


@app.route("/promotions/<int:promotion_id>/delete", methods=["POST"])
@login_required
@writer_required
def delete_promotion(promotion_id):
    db = get_db()
    promo = db.execute("SELECT * FROM promotion WHERE promotion_id = ?", (promotion_id,)).fetchone()
    if promo is None:
        abort(404)
    db.execute("DELETE FROM promotion WHERE promotion_id = ?", (promotion_id,))
    db.commit()
    flash("Promotion deleted.", "success")
    return redirect(url_for("view_partner", partner_id=promo["partner_id"]))


# ---------------------------------------------------------------------------
# READ — buildings reference list (read-only supporting view)
# ---------------------------------------------------------------------------
@app.route("/buildings")
@login_required
def list_buildings():
    db = get_db()
    buildings = db.execute(
        """SELECT b.*, COUNT(p.partner_id) AS partner_count
           FROM building b LEFT JOIN partner p ON p.building_id = b.building_id
           GROUP BY b.building_id ORDER BY b.name"""
    ).fetchall()
    return render_template("buildings.html", buildings=buildings)


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print("Database not found. Run `python init_db.py` first.")
    app.run(debug=True)
