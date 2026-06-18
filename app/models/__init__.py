"""
FreightFlow Nexus — Database Models
All entities: User, ShipperProfile, SupplierProfile, Driver, Vehicle,
Booking, Quote, Invoice, PurchaseOrder, Notification, AuditLog,
SupplierScoreHistory, BookingStatusEvent, AddressBook, AvailabilitySlot
"""
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
import bcrypt

db = SQLAlchemy()

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

# ─────────────────────────────────────────────────────────────────────────────
# USER & AUTH
# ─────────────────────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(20), nullable=False)   # shipper|supplier|driver|admin
    first_name    = db.Column(db.String(80))
    last_name     = db.Column(db.String(80))
    phone         = db.Column(db.String(30))
    is_active     = db.Column(db.Boolean, default=True)
    is_verified   = db.Column(db.Boolean, default=False)
    created_at    = db.Column(db.DateTime, default=utcnow)
    last_login    = db.Column(db.DateTime)

    # relationships
    shipper_profile  = db.relationship("ShipperProfile",  back_populates="user", uselist=False, cascade="all, delete")
    supplier_profile = db.relationship("SupplierProfile", back_populates="user", uselist=False, cascade="all, delete")
    driver_profile   = db.relationship("Driver",          back_populates="user", uselist=False, cascade="all, delete")
    admin_profile    = db.relationship("AdminProfile",    back_populates="user", uselist=False, cascade="all, delete")
    notifications    = db.relationship("Notification", back_populates="user", lazy="dynamic", cascade="all, delete")
    audit_logs       = db.relationship("AuditLog", back_populates="user", lazy="dynamic")

    def set_password(self, password: str):
        self.password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def check_password(self, password: str) -> bool:
        return bcrypt.checkpw(password.encode(), self.password_hash.encode())

    @property
    def full_name(self):
        return f"{self.first_name or ''} {self.last_name or ''}".strip() or self.email

    def __repr__(self):
        return f"<User {self.email} [{self.role}]>"


class ShipperProfile(db.Model):
    __tablename__ = "shipper_profiles"

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    account_type    = db.Column(db.String(20), default="Business")  # Business|Individual
    company_name    = db.Column(db.String(120))
    vat_number      = db.Column(db.String(30))
    industry        = db.Column(db.String(80))
    address         = db.Column(db.String(200))
    city            = db.Column(db.String(60))
    province        = db.Column(db.String(60))
    credit_limit    = db.Column(db.Float, default=0)
    credit_used     = db.Column(db.Float, default=0)
    total_spend     = db.Column(db.Float, default=0)
    health_score    = db.Column(db.Float, default=75.0)
    created_at      = db.Column(db.DateTime, default=utcnow)

    user            = db.relationship("User", back_populates="shipper_profile")
    bookings        = db.relationship("Booking", back_populates="shipper", lazy="dynamic")
    address_book    = db.relationship("AddressBook", back_populates="shipper", lazy="dynamic", cascade="all, delete")


class SupplierProfile(db.Model):
    __tablename__ = "supplier_profiles"

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    company_name    = db.Column(db.String(120), nullable=False)
    reg_number      = db.Column(db.String(40))
    vat_number      = db.Column(db.String(30))
    base_city       = db.Column(db.String(60))
    operating_region= db.Column(db.String(120))
    insurance_ref   = db.Column(db.String(80))
    bank_name       = db.Column(db.String(60))
    bank_account    = db.Column(db.String(30))
    bank_branch     = db.Column(db.String(20))
    account_holder  = db.Column(db.String(80))
    status          = db.Column(db.String(20), default="Under Review")  # Active|Suspended|Under Review
    score           = db.Column(db.Float, default=4.0)
    total_jobs      = db.Column(db.Integer, default=0)
    on_time_jobs    = db.Column(db.Integer, default=0)
    cancelled_jobs  = db.Column(db.Integer, default=0)
    acceptance_rate = db.Column(db.Float, default=95.0)
    created_at      = db.Column(db.DateTime, default=utcnow)
    approved_at     = db.Column(db.DateTime)

    user            = db.relationship("User", back_populates="supplier_profile")
    drivers         = db.relationship("Driver", back_populates="supplier", lazy="dynamic", cascade="all, delete")
    vehicles        = db.relationship("Vehicle", back_populates="supplier", lazy="dynamic", cascade="all, delete")
    quotes          = db.relationship("Quote", back_populates="supplier", lazy="dynamic")
    bookings        = db.relationship("Booking", back_populates="supplier", lazy="dynamic")
    score_history   = db.relationship("SupplierScoreHistory", back_populates="supplier", lazy="dynamic", cascade="all, delete")
    availability    = db.relationship("AvailabilitySlot", back_populates="supplier", lazy="dynamic", cascade="all, delete")

    @property
    def on_time_rate(self):
        if self.total_jobs == 0:
            return 100.0
        return round((self.on_time_jobs / self.total_jobs) * 100, 1)

    @property
    def cancellation_rate(self):
        if self.total_jobs == 0:
            return 0.0
        return round((self.cancelled_jobs / self.total_jobs) * 100, 1)


class AdminProfile(db.Model):
    __tablename__ = "admin_profiles"

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    department  = db.Column(db.String(40), default="Operations")  # Operations|Finance|Compliance|Tech|Management
    access_level= db.Column(db.String(20), default="Standard")    # Standard|Senior|Super

    user        = db.relationship("User", back_populates="admin_profile")


# ─────────────────────────────────────────────────────────────────────────────
# FLEET & DRIVERS
# ─────────────────────────────────────────────────────────────────────────────

class Driver(db.Model):
    __tablename__ = "drivers"

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)  # optional portal access
    supplier_id     = db.Column(db.Integer, db.ForeignKey("supplier_profiles.id"), nullable=False)
    name            = db.Column(db.String(80), nullable=False)
    id_number       = db.Column(db.String(20), unique=True)
    license_code    = db.Column(db.String(10), default="EC")
    license_expiry  = db.Column(db.Date)
    phone           = db.Column(db.String(20))
    status          = db.Column(db.String(20), default="Active")   # Active|Inactive|On Trip
    rating          = db.Column(db.Float, default=4.5)
    total_trips     = db.Column(db.Integer, default=0)
    created_at      = db.Column(db.DateTime, default=utcnow)

    user            = db.relationship("User", back_populates="driver_profile")
    supplier        = db.relationship("SupplierProfile", back_populates="drivers")
    bookings        = db.relationship("Booking", back_populates="driver", lazy="dynamic")


class Vehicle(db.Model):
    __tablename__ = "vehicles"

    id              = db.Column(db.Integer, primary_key=True)
    supplier_id     = db.Column(db.Integer, db.ForeignKey("supplier_profiles.id"), nullable=False)
    reg_number      = db.Column(db.String(20), unique=True, nullable=False)
    vehicle_type    = db.Column(db.String(60))   # Superlink|Horse & Trailer|8-Ton Rigid…
    payload_ton     = db.Column(db.Float)
    cbm             = db.Column(db.Float)
    year            = db.Column(db.Integer)
    roadworthy_expiry = db.Column(db.Date)
    availability    = db.Column(db.String(20), default="Available")  # Available|On Trip|Maintenance
    created_at      = db.Column(db.DateTime, default=utcnow)

    supplier        = db.relationship("SupplierProfile", back_populates="vehicles")
    bookings        = db.relationship("Booking", back_populates="vehicle", lazy="dynamic")


# ─────────────────────────────────────────────────────────────────────────────
# BOOKINGS & QUOTES
# ─────────────────────────────────────────────────────────────────────────────

class Booking(db.Model):
    __tablename__ = "bookings"

    id                  = db.Column(db.Integer, primary_key=True)
    ref                 = db.Column(db.String(20), unique=True, nullable=False, index=True)
    shipper_id          = db.Column(db.Integer, db.ForeignKey("shipper_profiles.id"), nullable=False)
    supplier_id         = db.Column(db.Integer, db.ForeignKey("supplier_profiles.id"))
    driver_id           = db.Column(db.Integer, db.ForeignKey("drivers.id"))
    vehicle_id          = db.Column(db.Integer, db.ForeignKey("vehicles.id"))
    accepted_quote_id   = db.Column(db.Integer, db.ForeignKey("quotes.id"))

    # Route
    collection_address  = db.Column(db.String(200))
    collection_city     = db.Column(db.String(60))
    delivery_address    = db.Column(db.String(200))
    delivery_city       = db.Column(db.String(60))
    route               = db.Column(db.String(120))   # "Durban → Johannesburg"
    distance_km         = db.Column(db.Float)

    # Cargo
    commodity           = db.Column(db.String(80))
    pieces              = db.Column(db.Integer)
    weight_per_item_kg  = db.Column(db.Float)
    total_weight_kg     = db.Column(db.Float)
    vehicle_type_req    = db.Column(db.String(60))
    destination_type    = db.Column(db.String(30))   # DC|Direct|Port

    # Contacts
    collection_contact  = db.Column(db.String(80))
    collection_phone    = db.Column(db.String(20))
    delivery_contact    = db.Column(db.String(80))
    delivery_phone      = db.Column(db.String(20))

    # Financials
    quoted_value        = db.Column(db.Float, default=0)
    platform_fee        = db.Column(db.Float, default=0)
    supplier_payout     = db.Column(db.Float, default=0)

    # Dates
    collection_date     = db.Column(db.Date)
    delivery_date       = db.Column(db.Date)
    created_at          = db.Column(db.DateTime, default=utcnow)
    confirmed_at        = db.Column(db.DateTime)
    collected_at        = db.Column(db.DateTime)
    delivered_at        = db.Column(db.DateTime)

    # Status
    status              = db.Column(db.String(30), default="Pending Quotes")
    # Pending Quotes | Quotes Received | Confirmed | Driver Assigned |
    # Collected | In Transit | Approaching Destination | Delivered | Cancelled

    risk_level          = db.Column(db.String(10), default="Low")  # Low|Medium|High
    notes               = db.Column(db.Text)
    pod_signed          = db.Column(db.Boolean, default=False)
    pod_signed_at       = db.Column(db.DateTime)

    # Relationships
    shipper     = db.relationship("ShipperProfile", back_populates="bookings")
    supplier    = db.relationship("SupplierProfile", back_populates="bookings")
    driver      = db.relationship("Driver", back_populates="bookings")
    vehicle     = db.relationship("Vehicle", back_populates="bookings")
    quotes      = db.relationship("Quote", back_populates="booking",
                                  primaryjoin="Booking.id == Quote.booking_id",
                                  foreign_keys="Quote.booking_id", lazy="dynamic", cascade="all, delete")
    status_events = db.relationship("BookingStatusEvent", back_populates="booking",
                                    order_by="BookingStatusEvent.created_at", cascade="all, delete")
    invoice     = db.relationship("Invoice", back_populates="booking", uselist=False, cascade="all, delete")
    purchase_order = db.relationship("PurchaseOrder", back_populates="booking", uselist=False, cascade="all, delete")

    def generate_ref(self):
        import random, string
        self.ref = "FFN-" + str(datetime.now().year) + "-" + ''.join(random.choices(string.digits, k=4))

    @property
    def total_weight(self):
        if self.pieces and self.weight_per_item_kg:
            return self.pieces * self.weight_per_item_kg
        return self.total_weight_kg or 0

    def calculate_platform_fee(self, pct=26.7):
        self.platform_fee  = round(self.quoted_value * (pct / 100), 2)
        self.supplier_payout = round(self.quoted_value - self.platform_fee, 2)


class Quote(db.Model):
    __tablename__ = "quotes"

    id              = db.Column(db.Integer, primary_key=True)
    booking_id      = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=False)
    supplier_id     = db.Column(db.Integer, db.ForeignKey("supplier_profiles.id"), nullable=False)
    amount          = db.Column(db.Float, nullable=False)
    transit_days    = db.Column(db.Integer)
    notes           = db.Column(db.Text)
    valid_until     = db.Column(db.DateTime)
    status          = db.Column(db.String(20), default="Pending")  # Pending|Accepted|Rejected|Expired
    ai_score        = db.Column(db.Float)     # composite AI ranking score
    rank            = db.Column(db.Integer)   # 1 = best
    created_at      = db.Column(db.DateTime, default=utcnow)

    booking         = db.relationship("Booking", back_populates="quotes",
                                      foreign_keys=[booking_id])
    supplier        = db.relationship("SupplierProfile", back_populates="quotes")


# ─────────────────────────────────────────────────────────────────────────────
# FINANCIALS
# ─────────────────────────────────────────────────────────────────────────────

class Invoice(db.Model):
    __tablename__ = "invoices"

    id              = db.Column(db.Integer, primary_key=True)
    booking_id      = db.Column(db.Integer, db.ForeignKey("bookings.id"), unique=True, nullable=False)
    invoice_number  = db.Column(db.String(30), unique=True, nullable=False)
    amount          = db.Column(db.Float)
    vat_amount      = db.Column(db.Float)
    total_amount    = db.Column(db.Float)
    status          = db.Column(db.String(20), default="Unpaid")  # Unpaid|Paid|Overdue
    due_date        = db.Column(db.Date)
    paid_at         = db.Column(db.DateTime)
    created_at      = db.Column(db.DateTime, default=utcnow)

    booking         = db.relationship("Booking", back_populates="invoice")

    def generate_number(self):
        self.invoice_number = f"INV-{datetime.now().year}-{self.id:05d}"


class PurchaseOrder(db.Model):
    __tablename__ = "purchase_orders"

    id              = db.Column(db.Integer, primary_key=True)
    booking_id      = db.Column(db.Integer, db.ForeignKey("bookings.id"), unique=True, nullable=False)
    po_number       = db.Column(db.String(30), unique=True, nullable=False)
    gross_amount    = db.Column(db.Float)
    platform_fee    = db.Column(db.Float)
    net_payable     = db.Column(db.Float)
    status          = db.Column(db.String(20), default="Pending")   # Pending|Approved|Paid
    approved_at     = db.Column(db.DateTime)
    paid_at         = db.Column(db.DateTime)
    created_at      = db.Column(db.DateTime, default=utcnow)

    booking         = db.relationship("Booking", back_populates="purchase_order")

    def generate_number(self):
        self.po_number = f"PO-{datetime.now().year}-{self.id:05d}"


# ─────────────────────────────────────────────────────────────────────────────
# TRACKING & EVENTS
# ─────────────────────────────────────────────────────────────────────────────

class BookingStatusEvent(db.Model):
    __tablename__ = "booking_status_events"

    id          = db.Column(db.Integer, primary_key=True)
    booking_id  = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=False)
    status      = db.Column(db.String(40), nullable=False)
    note        = db.Column(db.String(200))
    actor       = db.Column(db.String(80))   # who triggered this change
    lat         = db.Column(db.Float)
    lng         = db.Column(db.Float)
    created_at  = db.Column(db.DateTime, default=utcnow)

    booking     = db.relationship("Booking", back_populates="status_events")


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATIONS
# ─────────────────────────────────────────────────────────────────────────────

class Notification(db.Model):
    __tablename__ = "notifications"

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title       = db.Column(db.String(120), nullable=False)
    body        = db.Column(db.String(400))
    type        = db.Column(db.String(30), default="info")  # info|success|warning|error
    ref_type    = db.Column(db.String(20))   # booking|supplier|system
    ref_id      = db.Column(db.String(30))   # e.g. booking ref
    is_read     = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=utcnow)

    user        = db.relationship("User", back_populates="notifications")


# ─────────────────────────────────────────────────────────────────────────────
# ANALYTICS & INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

class SupplierScoreHistory(db.Model):
    __tablename__ = "supplier_score_history"

    id          = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("supplier_profiles.id"), nullable=False)
    score       = db.Column(db.Float, nullable=False)
    on_time_rate= db.Column(db.Float)
    cancel_rate = db.Column(db.Float)
    recorded_at = db.Column(db.DateTime, default=utcnow)

    supplier    = db.relationship("SupplierProfile", back_populates="score_history")


class AddressBook(db.Model):
    __tablename__ = "address_book"

    id          = db.Column(db.Integer, primary_key=True)
    shipper_id  = db.Column(db.Integer, db.ForeignKey("shipper_profiles.id"), nullable=False)
    label       = db.Column(db.String(80))
    address     = db.Column(db.String(200))
    city        = db.Column(db.String(60))
    contact_name= db.Column(db.String(80))
    contact_phone= db.Column(db.String(20))
    type        = db.Column(db.String(20), default="Delivery")  # Collection|Delivery

    shipper     = db.relationship("ShipperProfile", back_populates="address_book")


class AvailabilitySlot(db.Model):
    __tablename__ = "availability_slots"

    id          = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("supplier_profiles.id"), nullable=False)
    date        = db.Column(db.Date, nullable=False)
    vehicle_type= db.Column(db.String(60))
    slots_total = db.Column(db.Integer, default=1)
    slots_used  = db.Column(db.Integer, default=0)
    note        = db.Column(db.String(120))

    supplier    = db.relationship("SupplierProfile", back_populates="availability")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"))
    action      = db.Column(db.String(80))
    entity_type = db.Column(db.String(40))
    entity_id   = db.Column(db.String(40))
    detail      = db.Column(db.Text)
    ip_address  = db.Column(db.String(45))
    created_at  = db.Column(db.DateTime, default=utcnow)

    user        = db.relationship("User", back_populates="audit_logs")


# ─────────────────────────────────────────────────────────────────────────────
# COMPLAINTS
# ─────────────────────────────────────────────────────────────────────────────

class Complaint(db.Model):
    __tablename__ = "complaints"

    id              = db.Column(db.Integer, primary_key=True)
    ref             = db.Column(db.String(25), unique=True, nullable=False, index=True)

    # Who filed it
    shipper_id      = db.Column(db.Integer, db.ForeignKey("shipper_profiles.id"), nullable=False)
    # Related booking (optional but recommended)
    booking_id      = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=True)
    # Supplier the complaint is ultimately about
    supplier_id     = db.Column(db.Integer, db.ForeignKey("supplier_profiles.id"), nullable=True)

    category        = db.Column(db.String(80), nullable=False)
    priority        = db.Column(db.String(20), default="Normal")   # Normal|Urgent|Critical
    description     = db.Column(db.Text, nullable=False)
    evidence_files  = db.Column(db.String(400))   # comma-separated filenames

    # Workflow status
    # Submitted → Under Admin Review → Forwarded to Supplier → Supplier Responded → Resolved | Closed
    status          = db.Column(db.String(40), default="Submitted")

    # Admin actions
    admin_notes     = db.Column(db.Text)          # internal notes (not visible to supplier)
    forwarded_at    = db.Column(db.DateTime)       # when admin forwarded to supplier
    forwarded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    # Supplier response
    supplier_response  = db.Column(db.Text)
    supplier_responded_at = db.Column(db.DateTime)

    # Resolution
    resolution_notes = db.Column(db.Text)
    resolved_at      = db.Column(db.DateTime)

    created_at      = db.Column(db.DateTime, default=utcnow)
    updated_at      = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    # Relationships
    shipper         = db.relationship("ShipperProfile", foreign_keys=[shipper_id],
                                      backref=db.backref("complaints", lazy="dynamic"))
    booking         = db.relationship("Booking", foreign_keys=[booking_id],
                                      backref=db.backref("complaints", lazy="dynamic"))
    supplier        = db.relationship("SupplierProfile", foreign_keys=[supplier_id],
                                      backref=db.backref("complaints", lazy="dynamic"))
    forwarded_by    = db.relationship("User", foreign_keys=[forwarded_by_id])

    def generate_ref(self):
        import random, string
        self.ref = "CMP-" + str(datetime.now().year) + "-" + ''.join(random.choices(string.digits, k=5))

    @property
    def status_color(self):
        return {
            "Submitted":             "#1e40af",
            "Under Admin Review":    "#854d0e",
            "Forwarded to Supplier": "#7e22ce",
            "Supplier Responded":    "#065f46",
            "Resolved":              "#166534",
            "Closed":                "#374151",
        }.get(self.status, "#374151")
