"""
wsgi.py — production entry point for hosting (e.g. Render, Railway, Heroku).

Gunicorn imports `app` from here. Before serving, it ensures the SQLite
database exists by running the initializer once if the file is missing.
On a fresh free-tier host the filesystem starts empty, so this guarantees the
app has data to serve without a manual build step.
"""
import os
import init_db
from app import app

# Build the database on first boot if it isn't there yet.
if not os.path.exists(init_db.DB_PATH):
    init_db.main()

if __name__ == "__main__":
    app.run()
