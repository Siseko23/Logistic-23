"""
FreightFlow Nexus — Application Factory
"""
from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mail import Mail

from config import config
from app.models import db, User, Complaint  # noqa: F401 — ensure Complaint is in metadata

login_manager = LoginManager()
migrate       = Migrate()
mail          = Mail()


def create_app(config_name="default"):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config[config_name])

    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    from app.routes.auth     import auth_bp
    from app.routes.shipper  import shipper_bp
    from app.routes.supplier import supplier_bp
    from app.routes.admin    import admin_bp
    from app.routes.driver   import driver_bp
    from app.routes.public   import public_bp, api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(shipper_bp,  url_prefix="/shipper")
    app.register_blueprint(supplier_bp, url_prefix="/supplier")
    app.register_blueprint(admin_bp,    url_prefix="/admin")
    app.register_blueprint(driver_bp,   url_prefix="/driver")
    app.register_blueprint(public_bp)
    app.register_blueprint(api_bp,      url_prefix="/api")

    # Jinja helpers — registered as BOTH filters and globals so templates
    # can use either {{ value | zar }} or {{ zar(value) }}
    def _zar(value):
        try:
            return f"R {float(value):,.2f}"
        except (TypeError, ValueError):
            return "R 0.00"

    def _pct(value):
        try:
            return f"{float(value):.1f}%"
        except (TypeError, ValueError):
            return "0%"

    app.template_filter("zar")(_zar)
    app.template_filter("pct")(_pct)
    app.jinja_env.globals["zar"] = _zar
    app.jinja_env.globals["pct"] = _pct

    # enumerate_filter: used in v19 templates as `list | enumerate_filter`
    # returns list of (index, item) tuples — same as Python enumerate()
    app.jinja_env.filters["enumerate_filter"] = lambda iterable: list(enumerate(iterable))
    app.jinja_env.globals["enumerate"] = enumerate

    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        from app.models import Notification
        from datetime import timedelta

        role = None
        user = None
        bell_notifications = []
        bell_count = 0

        if current_user.is_authenticated:
            role = current_user.role
            user = current_user.full_name or current_user.email

            # Build bell notifications matching v19 format
            raw = current_user.notifications\
                      .order_by(Notification.created_at.desc()).limit(6).all()
            bell_count = current_user.notifications.filter_by(is_read=False).count()

            icon_map = {"success":"✅", "warning":"⚠️", "error":"❌", "info":"ℹ️"}
            for n in raw:
                # human-readable time delta
                from datetime import datetime
                delta = datetime.utcnow() - n.created_at
                if delta.seconds < 3600:
                    t = f"{delta.seconds // 60}m ago"
                elif delta.days == 0:
                    t = f"{delta.seconds // 3600}h ago"
                else:
                    t = f"{delta.days}d ago"

                bell_notifications.append({
                    "id":     n.id,
                    "title":  n.title,
                    "detail": n.body[:60] + "…" if n.body and len(n.body) > 60 else n.body or "",
                    "time":   t,
                    "icon":   icon_map.get(n.type, "ℹ️"),
                    "read":   n.is_read,
                    "link":   "#",
                })

        return dict(
            role=role,
            user=user,
            bell_notifications=bell_notifications,
            bell_count=bell_count,
            unread_notifications=bell_count,
        )

    return app
