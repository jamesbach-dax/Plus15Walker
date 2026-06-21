#!/usr/bin/env bash
# Convenience launcher: sets up the database (if needed) and starts Flask.
set -e
python init_db.py
python app.py
