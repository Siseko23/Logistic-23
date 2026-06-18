"""
FreightFlow Nexus — Celery Background Pipelines
Tasks: booking scoring, supplier score recalc, notification dispatch,
       invoice generation, health score refresh, risk flagging.
"""
from celery import Celery
from celery.schedules import crontab


def make_celery(app):
    celery = Celery(app.import_name,
                    broker=app.config["CELERY_BROKER_URL"],
                    backend=app.config["CELERY_RESULT_BACKEND"])
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask

    # ── Periodic beat schedule ────────────────────────────────────────────────
    celery.conf.beat_schedule = {
        # Recalculate all supplier scores every hour
        "recalc-supplier-scores": {
            "task":     "app.pipelines.tasks.recalc_all_supplier_scores",
            "schedule": crontab(minute=0),
        },
        # Refresh shipper health scores every 6 hours
        "refresh-health-scores": {
            "task":     "app.pipelines.tasks.refresh_all_health_scores",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        # Flag high-risk bookings every 30 minutes
        "flag-risky-bookings": {
            "task":     "app.pipelines.tasks.flag_risky_bookings",
            "schedule": crontab(minute="*/30"),
        },
        # Expire old quotes daily at midnight
        "expire-old-quotes": {
            "task":     "app.pipelines.tasks.expire_old_quotes",
            "schedule": crontab(hour=0, minute=0),
        },
        # Generate daily platform report at 07:00
        "daily-platform-report": {
            "task":     "app.pipelines.tasks.daily_platform_summary",
            "schedule": crontab(hour=7, minute=0),
        },
    }

    return celery
