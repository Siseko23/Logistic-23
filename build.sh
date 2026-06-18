#!/usr/bin/env bash
set -e

pip install -r requirements.txt

# Seed the database if it doesn't exist yet (first deploy)
if [ ! -f "freightflow.db" ]; then
  echo "🌱 First deploy — seeding database..."
  python seeds/seed.py
  echo "✅ Seed complete"
else
  echo "✅ Database already exists — skipping seed"
  # Still ensure any new tables (e.g. complaints) are created
  python - << 'PY'
import os, sys
sys.path.insert(0, os.getcwd())
os.environ.setdefault("FLASK_ENV", "production")
from app import create_app
from app.models import db
app = create_app("production")
with app.app_context():
    db.create_all()
    print("✅ Schema up to date")
PY
fi
