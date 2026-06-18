"""
FreightFlow Nexus — Database Seed Script
Run: python seeds/seed.py

Seeds:
  - 1 admin
  - 5 suppliers (Active) + 1 Under Review
  - 4 shippers (Business) + 2 (Individual)
  - 3 drivers per supplier
  - 2–4 vehicles per supplier
  - 30 bookings across various statuses
  - Quotes, invoices, purchase orders, status events
  - Supplier score history (6 weeks)
  - Notifications
  - Audit log entries
"""
import sys, os, random
from datetime import datetime, date, timedelta

# Ensure the project root is on the path regardless of where the script is called from
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)  # important: SQLite relative path resolves from CWD

from app import create_app
from app.models import (db, User, ShipperProfile, SupplierProfile, AdminProfile,
                         Driver, Vehicle, Booking, Quote, Invoice, PurchaseOrder,
                         BookingStatusEvent, Notification, AuditLog,
                         SupplierScoreHistory, AddressBook, AvailabilitySlot)

app = create_app("development")

# ── Seed data ─────────────────────────────────────────────────────────────────

SUPPLIERS_DATA = [
    {"company":"Kopano Linehaul (Pty) Ltd","city":"Johannesburg","region":"Gauteng / KZN","score":4.7,"status":"Active","reg":"2014/112233/07"},
    {"company":"Highveld Haulage CC",      "city":"Pretoria",    "region":"Gauteng / Limpopo","score":4.4,"status":"Active","reg":"2016/445566/23"},
    {"company":"Blue Crane Logistics",     "city":"Durban",      "region":"KwaZulu-Natal","score":3.8,"status":"Active","reg":"2018/778899/07"},
    {"company":"Savanna Freight Co.",      "city":"Cape Town",   "region":"Western Cape","score":4.2,"status":"Active","reg":"2019/334455/07"},
    {"company":"Natal Bulk Movers",        "city":"Durban",      "region":"KwaZulu-Natal","score":4.0,"status":"Active","reg":"2020/556677/07"},
    {"company":"SA Express Freight",       "city":"Gqeberha",    "region":"Eastern Cape","score":3.5,"status":"Under Review","reg":"2022/998877/07"},
]

SHIPPERS_DATA = [
    {"name":"Ubuntu Retail Group",     "type":"Business", "city":"Durban",       "province":"KwaZulu-Natal","email":"ops@ubunturetail.co.za"},
    {"name":"Cape Fresh Produce",      "type":"Business", "city":"Cape Town",    "province":"Western Cape","email":"logistics@capefresh.co.za"},
    {"name":"JHB Steel & Materials",   "type":"Business", "city":"Johannesburg", "province":"Gauteng","email":"freight@jhbsteel.co.za"},
    {"name":"Ntombi Dlamini Trading",  "type":"Individual","city":"Durban",      "province":"KwaZulu-Natal","email":"ntombi@gmail.com"},
    {"name":"Savannah Mining Supplies","type":"Business", "city":"Polokwane",    "province":"Limpopo","email":"supply@savannahmining.co.za"},
    {"name":"Lucky Sithole Transport", "type":"Individual","city":"Soweto",      "province":"Gauteng","email":"lucky@hotmail.com"},
]

ROUTES = [
    ("Durban","Johannesburg",588,14800),
    ("Cape Town","Gqeberha",762,8900),
    ("Johannesburg","Polokwane",278,11500),
    ("Durban","Cape Town",1753,38000),
    ("Pretoria","Durban",588,14200),
    ("Johannesburg","Bloemfontein",399,9800),
    ("Durban","Pretoria",608,15100),
    ("Cape Town","Johannesburg",1402,34000),
]

VEHICLE_TYPES = [
    ("Superlink (34-Ton)", 34, 120),
    ("Horse & Trailer (22-Ton)", 22, 80),
    ("8-Ton Rigid", 8, 40),
    ("Curtainsider (8-Ton)", 8, 42),
    ("Flat-Deck / Lowbed", 30, 0),
]

COMMODITIES = [
    "General freight","FMCG goods","Steel coils","Frozen produce",
    "Automotive parts","Construction materials","Retail stock",
    "Mining equipment","Chemical drums","Paper & pulp",
]

DRIVER_NAMES = [
    "Siphamandla Thusi","Bongani Nkosi","Thabang Mokoena","Lucky Dlamini",
    "Nkosinathi Zulu","Sifiso Ndlovu","Lungelo Mkhize","Themba Cele",
    "Musa Ntuli","Siyanda Gumede","Phiwayinkosi Mthembu","Lindani Khoza",
    "Vusi Maluleke","Tshepiso Motaung","Lungani Shabalala","Mpendulo Mchunu",
]


def create_user(email, password, role, first, last, phone=None):
    if User.query.filter_by(email=email).first():
        print(f"  ↳ User {email} already exists, skipping")
        return None
    u = User(email=email, role=role, first_name=first, last_name=last,
             phone=phone, is_active=True, is_verified=True)
    u.set_password(password)
    db.session.add(u)
    db.session.flush()
    return u


def seed_all():
    with app.app_context():
        print("\n🌱 FreightFlow Nexus — Seed Script")
        print("=" * 50)

        db.drop_all()
        db.create_all()
        print("✅ Tables created")

        # ── Admin ──────────────────────────────────────────────────────────────
        print("\n[1/8] Seeding admin...")
        admin_user = create_user("admin@movement.com", "admin1234", "admin",
                                  "Sipho", "Ndlovu", "+27 11 000 0001")
        if admin_user:
            profile = AdminProfile(user_id=admin_user.id, department="Operations",
                                    access_level="Super")
            db.session.add(profile)
            db.session.flush()
            print(f"  ✅ Admin: admin@movement.com / admin1234")

        # ── Suppliers ─────────────────────────────────────────────────────────
        print("\n[2/8] Seeding suppliers...")
        supplier_profiles = []
        for i, s in enumerate(SUPPLIERS_DATA):
            email = f"supplier{i+1}@{s['company'].lower().replace(' ','').replace('(pty)ltd','').replace('cc','')[:12]}.co.za"
            email = f"supplier{i+1}@movement.com"
            user  = create_user(email, "supplier123", "supplier",
                                 s["company"].split()[0], "Manager", f"+27 31 {100+i:03d} 0000")
            if user:
                sp = SupplierProfile(
                    user_id=user.id, company_name=s["company"], reg_number=s["reg"],
                    base_city=s["city"], operating_region=s["region"],
                    status=s["status"], score=s["score"],
                    bank_name="First National Bank", bank_account=f"620{random.randint(1000000,9999999)}",
                    bank_branch="250655", account_holder=s["company"],
                    insurance_ref=f"INS-{random.randint(10000,99999)}",
                    acceptance_rate=round(random.uniform(88, 98), 1),
                )
                if s["status"] == "Active":
                    sp.approved_at = datetime.utcnow() - timedelta(days=random.randint(30,365))
                    sp.total_jobs  = random.randint(20, 150)
                    sp.on_time_jobs = int(sp.total_jobs * random.uniform(0.78, 0.97))
                db.session.add(sp)
                db.session.flush()
                supplier_profiles.append(sp)
                print(f"  ✅ {s['company']} [{s['status']}] → {email}")

        # ── Score history for suppliers ────────────────────────────────────────
        print("   → Seeding score history...")
        for sp in supplier_profiles:
            base = sp.score
            for week in range(6, 0, -1):
                variation  = random.uniform(-0.15, 0.10)
                hist_score = max(2.5, min(5.0, round(base + variation * week * 0.3, 2)))
                hist = SupplierScoreHistory(
                    supplier_id=sp.id,
                    score=hist_score,
                    on_time_rate=round(random.uniform(78, 97), 1),
                    cancel_rate=round(random.uniform(1, 8), 1),
                    recorded_at=datetime.utcnow() - timedelta(weeks=week)
                )
                db.session.add(hist)

        # ── Drivers ───────────────────────────────────────────────────────────
        print("\n[3/8] Seeding drivers...")
        driver_name_pool = DRIVER_NAMES[:]
        random.shuffle(driver_name_pool)
        name_idx = 0
        all_drivers = []
        for sp in supplier_profiles[:5]:  # only active suppliers
            for _ in range(3):
                if name_idx >= len(driver_name_pool):
                    break
                name   = driver_name_pool[name_idx]; name_idx += 1
                parts  = name.split()
                d = Driver(
                    supplier_id  = sp.id,
                    name         = name,
                    id_number    = f"{random.randint(800101,991231):06d}{random.randint(5000,6999):04d}08{random.randint(0,9)}",
                    license_code = random.choice(["EC","C","EB"]),
                    license_expiry = date.today() + timedelta(days=random.randint(90, 730)),
                    phone        = f"+27 8{random.randint(1,9)} {random.randint(100,999)} {random.randint(1000,9999)}",
                    status       = random.choice(["Active","Active","Active","On Trip"]),
                    rating       = round(random.uniform(3.8, 4.9), 1),
                    total_trips  = random.randint(10, 200),
                )
                db.session.add(d)
                all_drivers.append((sp.id, d))
        db.session.flush()
        print(f"  ✅ {len(all_drivers)} drivers created")

        # ── Vehicles ──────────────────────────────────────────────────────────
        print("\n[4/8] Seeding fleet...")
        all_vehicles = []
        reg_counter  = 1000
        for sp in supplier_profiles[:5]:
            num_vehicles = random.randint(2, 4)
            for _ in range(num_vehicles):
                vtype, payload, cbm = random.choice(VEHICLE_TYPES)
                prov_code = random.choice(["ND","GP","WC","EC","LP"])
                reg_num   = f"{prov_code} {reg_counter}-{random.randint(100,999)}"
                reg_counter += 1
                v = Vehicle(
                    supplier_id   = sp.id,
                    reg_number    = reg_num,
                    vehicle_type  = vtype,
                    payload_ton   = payload,
                    cbm           = cbm,
                    year          = random.randint(2015, 2023),
                    roadworthy_expiry = date.today() + timedelta(days=random.randint(30, 540)),
                    availability  = random.choice(["Available","Available","On Trip"]),
                )
                db.session.add(v)
                all_vehicles.append((sp.id, v))
        db.session.flush()
        print(f"  ✅ {len(all_vehicles)} vehicles created")

        # ── Shippers ──────────────────────────────────────────────────────────
        print("\n[5/8] Seeding shippers...")
        shipper_profiles = []
        for i, s in enumerate(SHIPPERS_DATA):
            email = f"shipper{i+1}@movement.com"
            parts = s["name"].split()
            user  = create_user(email, "shipper123", "shipper",
                                 parts[0], parts[-1], f"+27 3{i} 000 000{i}")
            if user:
                sp = ShipperProfile(
                    user_id=user.id, account_type=s["type"],
                    company_name=s["name"], city=s["city"], province=s["province"],
                    industry=random.choice(["Retail","Agriculture","Mining","Manufacturing","FMCG","Construction"]),
                    address=f"{random.randint(1,200)} {random.choice(['Main St','Park Ave','Industrial Rd','Commerce Dr'])}, {s['city']}",
                    total_spend=0, health_score=round(random.uniform(65, 92), 1),
                )
                db.session.add(sp)
                db.session.flush()
                shipper_profiles.append(sp)

                # Address book entries
                for j in range(2):
                    addr = AddressBook(
                        shipper_id=sp.id,
                        label=f"Warehouse {j+1}",
                        address=f"{random.randint(1,500)} Industrial Rd",
                        city=random.choice(["Durban","Johannesburg","Cape Town","Pretoria"]),
                        contact_name=f"Contact {j+1}",
                        contact_phone=f"+27 8{j} 000 000{j}",
                        type=random.choice(["Collection","Delivery"]),
                    )
                    db.session.add(addr)

                print(f"  ✅ {s['name']} [{s['type']}] → {email}")

        # ── Bookings ──────────────────────────────────────────────────────────
        print("\n[6/8] Seeding bookings...")
        STATUSES = [
            "Delivered","Delivered","Delivered","Delivered",
            "In Transit","In Transit",
            "Confirmed","Driver Assigned",
            "Pending Quotes","Quotes Received",
            "Cancelled",
        ]
        bookings_created = []

        for i in range(30):
            shipper  = random.choice(shipper_profiles)
            supplier = random.choice(supplier_profiles[:5])  # active only
            col_city, del_city, dist_km, base_rate = random.choice(ROUTES)
            commodity = random.choice(COMMODITIES)
            amount    = round(base_rate * random.uniform(0.88, 1.18), -2)
            pieces    = random.randint(1, 24)
            weight    = random.uniform(200, 2000)
            status    = random.choice(STATUSES)

            created_ago = timedelta(days=random.randint(1, 90))
            created_at  = datetime.utcnow() - created_ago

            b = Booking(
                shipper_id         = shipper.id,
                route              = f"{col_city} → {del_city}",
                collection_city    = col_city,
                delivery_city      = del_city,
                collection_address = f"{random.randint(1,200)} Depot Rd, {col_city}",
                delivery_address   = f"{random.randint(1,200)} Warehouse Blvd, {del_city}",
                distance_km        = dist_km,
                commodity          = commodity,
                pieces             = pieces,
                weight_per_item_kg = round(weight / pieces, 1),
                total_weight_kg    = weight,
                vehicle_type_req   = random.choice([t[0] for t in VEHICLE_TYPES]),
                destination_type   = random.choice(["DC","Direct","Port"]),
                collection_contact = f"{random.choice(['Sipho','Nomsa','Thabo','Zanele'])} {random.choice(['Nkosi','Dlamini','Zulu','Mthembu'])}",
                collection_phone   = f"+27 8{random.randint(1,9)} {random.randint(100,999)} {random.randint(1000,9999)}",
                delivery_contact   = f"{random.choice(['Lerato','Bhekani','Mpho','Nandi'])} {random.choice(['Mokoena','Cele','Ndlovu','Sithole'])}",
                delivery_phone     = f"+27 8{random.randint(1,9)} {random.randint(100,999)} {random.randint(1000,9999)}",
                quoted_value       = amount if status != "Pending Quotes" else 0,
                collection_date    = (created_at + timedelta(days=1)).date(),
                status             = status,
                created_at         = created_at,
                risk_level         = random.choice(["Low","Low","Medium","High"]),
                notes              = random.choice(["","Handle with care","DC slot 08:00–10:00",""]),
            )
            b.generate_ref()

            if status not in ("Pending Quotes","Quotes Received","Cancelled"):
                b.supplier_id   = supplier.id
                b.confirmed_at  = created_at + timedelta(hours=random.randint(2, 24))
                b.calculate_platform_fee()
                shipper.total_spend = (shipper.total_spend or 0) + amount

                # Assign driver and vehicle from this supplier
                sup_drivers  = [(sid, d) for sid, d in all_drivers if sid == supplier.id]
                sup_vehicles = [(sid, v) for sid, v in all_vehicles if sid == supplier.id]
                if sup_drivers:
                    b.driver_id = random.choice(sup_drivers)[1].id
                if sup_vehicles:
                    b.vehicle_id = random.choice(sup_vehicles)[1].id

                if status in ("Collected","In Transit","Approaching Destination","Delivered"):
                    b.collected_at = b.confirmed_at + timedelta(hours=random.randint(12, 48))
                if status == "Delivered":
                    b.delivered_at = b.collected_at + timedelta(hours=random.randint(6, 72)) if b.collected_at else b.confirmed_at + timedelta(days=2)
                    b.pod_signed   = True

            db.session.add(b)
            db.session.flush()
            bookings_created.append(b)

            # Status events
            event_map = {
                "Confirmed":   ["Pending Quotes","Quotes Received","Confirmed"],
                "Driver Assigned": ["Pending Quotes","Quotes Received","Confirmed","Driver Assigned"],
                "Collected":   ["Pending Quotes","Quotes Received","Confirmed","Driver Assigned","Collected"],
                "In Transit":  ["Pending Quotes","Quotes Received","Confirmed","Driver Assigned","Collected","In Transit"],
                "Delivered":   ["Pending Quotes","Quotes Received","Confirmed","Driver Assigned","Collected","In Transit","Approaching Destination","Delivered"],
                "Cancelled":   ["Pending Quotes","Cancelled"],
            }
            event_statuses = event_map.get(status, [status])
            t = created_at
            for ev_status in event_statuses:
                t += timedelta(hours=random.randint(1,12))
                ev = BookingStatusEvent(booking_id=b.id, status=ev_status,
                                         note=f"Status updated to {ev_status}",
                                         actor="System", created_at=t)
                db.session.add(ev)

            # Quotes
            if status != "Pending Quotes":
                for sup in random.sample(supplier_profiles[:5], k=random.randint(2,4)):
                    q_amount = round(amount * random.uniform(0.85, 1.20), -2)
                    q_status = "Accepted" if (sup.id == supplier.id and status not in ("Quotes Received","Cancelled")) else "Pending"
                    if status == "Cancelled":
                        q_status = "Expired"
                    q = Quote(
                        booking_id  = b.id,
                        supplier_id = sup.id,
                        amount      = q_amount,
                        transit_days= random.randint(1, 4),
                        status      = q_status,
                        ai_score    = round(random.uniform(0.4, 0.9), 4),
                        rank        = random.randint(1, 4),
                        created_at  = created_at + timedelta(hours=random.randint(1, 8)),
                    )
                    db.session.add(q)

        db.session.flush()
        print(f"  ✅ {len(bookings_created)} bookings created")

        # ── Invoices & Purchase Orders ─────────────────────────────────────────
        print("\n[7/8] Seeding invoices & POs...")
        inv_count = 0
        for b in bookings_created:
            if b.status == "Delivered" and b.quoted_value:
                vat     = round(b.quoted_value * 0.15, 2)
                total   = round(b.quoted_value + vat, 2)
                inv = Invoice(
                    booking_id     = b.id,
                    invoice_number = f"INV-{b.created_at.year}-{b.id:05d}",
                    amount         = b.quoted_value,
                    vat_amount     = vat,
                    total_amount   = total,
                    status         = random.choice(["Paid","Paid","Unpaid","Overdue"]),
                    due_date       = (b.delivered_at or datetime.utcnow()).date() + timedelta(days=30),
                    paid_at        = b.delivered_at if random.random() > 0.3 else None,
                    created_at     = b.delivered_at or datetime.utcnow(),
                )
                db.session.add(inv)

                po = PurchaseOrder(
                    booking_id   = b.id,
                    po_number    = f"PO-{b.created_at.year}-{b.id:05d}",
                    gross_amount = b.quoted_value,
                    platform_fee = b.platform_fee,
                    net_payable  = b.supplier_payout,
                    status       = random.choice(["Paid","Paid","Pending","Approved"]),
                    created_at   = b.delivered_at or datetime.utcnow(),
                )
                db.session.add(po)
                inv_count += 1

        db.session.flush()
        print(f"  ✅ {inv_count} invoices + POs created")

        # ── Notifications & Audit logs ────────────────────────────────────────
        print("\n[8/8] Seeding notifications & audit logs...")
        all_users = User.query.all()
        notif_messages = [
            ("New booking confirmed", "Your booking has been confirmed.", "success"),
            ("Quote received", "A new supplier quote is ready for review.", "info"),
            ("Driver assigned", "A driver has been assigned to your shipment.", "info"),
            ("Shipment delivered", "Your cargo has been delivered successfully.", "success"),
            ("Invoice generated", "A new invoice is ready for payment.", "info"),
            ("⚠️ Delivery risk flagged", "One of your active bookings has been flagged as high risk.", "warning"),
            ("Platform update", "FreightFlow Nexus v17 features are now live.", "info"),
        ]
        for user in all_users:
            for j in range(random.randint(2, 5)):
                title, body, ntype = random.choice(notif_messages)
                n = Notification(
                    user_id=user.id, title=title, body=body, type=ntype,
                    is_read=random.random() > 0.4,
                    created_at=datetime.utcnow() - timedelta(days=random.randint(0, 14))
                )
                db.session.add(n)

        audit_actions = ["LOGIN","CREATE_BOOKING","ACCEPT_QUOTE","DISPATCH","SUBMIT_QUOTE","APPROVE_SUPPLIER"]
        for i in range(40):
            user = random.choice(all_users)
            a = AuditLog(
                user_id=user.id,
                action=random.choice(audit_actions),
                entity_type=random.choice(["Booking","SupplierProfile","Quote","User"]),
                entity_id=f"FFN-2026-{random.randint(1000,9999)}",
                ip_address=f"41.{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}",
                created_at=datetime.utcnow() - timedelta(hours=random.randint(0, 720))
            )
            db.session.add(a)

        # ── Availability slots ────────────────────────────────────────────────
        for sp in supplier_profiles[:5]:
            for day_offset in range(14):
                if random.random() > 0.4:
                    slot = AvailabilitySlot(
                        supplier_id  = sp.id,
                        date         = date.today() + timedelta(days=day_offset),
                        vehicle_type = random.choice([t[0] for t in VEHICLE_TYPES]),
                        slots_total  = random.randint(1, 3),
                        slots_used   = random.randint(0, 1),
                    )
                    db.session.add(slot)

        db.session.commit()

        # ── Summary ───────────────────────────────────────────────────────────
        print("\n" + "=" * 50)
        print("✅ SEED COMPLETE")
        print("=" * 50)
        print(f"  Users:     {User.query.count()}")
        print(f"  Suppliers: {SupplierProfile.query.count()}")
        print(f"  Shippers:  {ShipperProfile.query.count()}")
        print(f"  Drivers:   {Driver.query.count()}")
        print(f"  Vehicles:  {Vehicle.query.count()}")
        print(f"  Bookings:  {Booking.query.count()}")
        print(f"  Quotes:    {Quote.query.count()}")
        print(f"  Invoices:  {Invoice.query.count()}")
        print(f"  POs:       {PurchaseOrder.query.count()}")
        print(f"  Notifs:    {Notification.query.count()}")
        print(f"  Audit:     {AuditLog.query.count()}")
        print()
        print("LOGIN CREDENTIALS:")
        print("  Admin:    admin@movement.com    / admin1234")
        print("  Shipper:  shipper1@movement.com / shipper123")
        print("  Supplier: supplier1@movement.com / supplier123")
        print("=" * 50)


if __name__ == "__main__":
    seed_all()
