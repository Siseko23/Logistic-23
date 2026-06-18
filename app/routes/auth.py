"""
Auth blueprint: /register  /login  /logout  /verify
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timezone

from app.models import db, User, ShipperProfile, SupplierProfile, AdminProfile, Driver
from app.services.notifications import push_notification
from app.services.audit import log_action

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

ROLE_DASHBOARDS = {
    "shipper":  "shipper.dashboard",
    "supplier": "supplier.dashboard",
    "driver":   "driver.dashboard",
    "admin":    "admin.dashboard",
}

# ── Register ──────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(_role_home())

    if request.method == "POST":
        email      = request.form.get("email", "").strip().lower()
        password   = request.form.get("password", "")
        confirm    = request.form.get("confirm_password", "")
        role       = request.form.get("role", "shipper")
        first_name = request.form.get("first_name", "").strip()
        last_name  = request.form.get("last_name", "").strip()
        phone      = request.form.get("phone", "").strip()

        # Validation
        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("auth/register.html")
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("auth/register.html")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("auth/register.html")
        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
            return render_template("auth/register.html")
        if role not in ("shipper", "supplier", "admin", "driver"):
            flash("Invalid role selected.", "error")
            return render_template("auth/register.html")

        # Create user
        user = User(email=email, role=role, first_name=first_name,
                    last_name=last_name, phone=phone)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()  # get user.id before commit

        # Create role profile
        if role == "shipper":
            account_type = request.form.get("account_type", "Business")
            company_name = request.form.get("company_name", "").strip()
            profile = ShipperProfile(user_id=user.id, account_type=account_type,
                                     company_name=company_name)
            db.session.add(profile)

        elif role == "supplier":
            company_name = request.form.get("company_name", "").strip()
            base_city    = request.form.get("base_city", "").strip()
            profile = SupplierProfile(user_id=user.id, company_name=company_name,
                                      base_city=base_city, status="Under Review")
            db.session.add(profile)

        elif role == "admin":
            department = request.form.get("department", "Operations")
            profile = AdminProfile(user_id=user.id, department=department)
            db.session.add(profile)

        elif role == "driver":
            # drivers are created by suppliers; this is a minimal self-registration
            # supplier_id must be set later by admin
            pass

        db.session.commit()

        push_notification(user.id, "Welcome to FreightFlow Nexus!",
                          f"Your {role} account is ready. Start exploring the platform.",
                          type="success")
        log_action(user.id, "REGISTER", "User", str(user.id), f"Role: {role}")

        login_user(user)
        flash(f"Welcome, {user.full_name}! Your account has been created.", "success")
        return redirect(_role_home())

    return render_template("auth/register.html")


# ── Login ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_role_home())

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash("Invalid email or password.", "error")
            log_action(None, "LOGIN_FAIL", "User", email, "Bad credentials")
            return render_template("login.html")

        if not user.is_active:
            flash("Your account has been suspended. Contact support@movement.com.", "error")
            return render_template("login.html")

        user.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
        login_user(user, remember=remember)
        log_action(user.id, "LOGIN", "User", str(user.id))

        next_page = request.args.get("next")
        if next_page and next_page.startswith("/"):
            return redirect(next_page)
        return redirect(_role_home())

    return render_template("login.html")


# ── Logout ────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout")
@login_required
def logout():
    log_action(current_user.id, "LOGOUT", "User", str(current_user.id))
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


# ── Profile / change password ─────────────────────────────────────────────────

@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "update_name":
            current_user.first_name = request.form.get("first_name", "").strip()
            current_user.last_name  = request.form.get("last_name", "").strip()
            current_user.phone      = request.form.get("phone", "").strip()
            db.session.commit()
            flash("Profile updated.", "success")
        elif action == "change_password":
            current_pw = request.form.get("current_password", "")
            new_pw     = request.form.get("new_password", "")
            confirm_pw = request.form.get("confirm_password", "")
            if not current_user.check_password(current_pw):
                flash("Current password is incorrect.", "error")
            elif new_pw != confirm_pw:
                flash("New passwords do not match.", "error")
            elif len(new_pw) < 8:
                flash("Password must be at least 8 characters.", "error")
            else:
                current_user.set_password(new_pw)
                db.session.commit()
                flash("Password changed successfully.", "success")

    return render_template("shipper/profile.html", title="My Profile", user=current_user)


# ── Helper ────────────────────────────────────────────────────────────────────

def _role_home():
    return url_for(ROLE_DASHBOARDS.get(current_user.role, "public.index"))
