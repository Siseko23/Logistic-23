"""
FreightFlow Nexus — Entry Point

Commands:
  Run dev server:    python run.py
  Seed database:     python seeds/seed.py
  Run Celery worker: celery -A run.celery worker --loglevel=info
  Run Celery beat:   celery -A run.celery beat --loglevel=info
"""
import os
from app import create_app
from app.models import db

_env   = os.getenv("FLASK_ENV", "development")
app    = create_app("production" if _env == "production" else "development")

# Make Celery importable (only used if Redis is available)
try:
    from app.pipelines.celery_app import make_celery
    celery = make_celery(app)
except Exception:
    celery = None

# ── Auto-create tables if DB doesn't exist yet ─────────────────────────────
with app.app_context():
    db_path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
    if not os.path.exists(db_path):
        print("⚙️  Database not found — creating tables...")
        db.create_all()
        print("✅ Tables created. Run `python seeds/seed.py` to populate demo data.")
    else:
        # Ensure any new tables added to models are created
        db.create_all()

if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")
