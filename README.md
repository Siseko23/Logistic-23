# FreightFlow Nexus — Full Stack v19

AI-powered freight marketplace. Flask + SQLite + Flask-Login + v19 UI.

---

## Quick start (Windows / Mac / Linux)

### 1. Create a virtual environment
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac / Linux
source .venv/bin/activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Seed the database (creates all tables + demo data)
```bash
python seeds/seed.py
```

You should see:
```
✅ Tables created
✅ Admin: admin@movement.com / admin1234
✅ 30 bookings created
✅ SEED COMPLETE
```

### 4. Run the server
```bash
python run.py
```

Open http://localhost:5000

---

## Demo login credentials

| Role     | Email                        | Password     |
|----------|------------------------------|--------------|
| Admin    | admin@movement.com           | admin1234    |
| Shipper  | shipper1@movement.com        | shipper123   |
| Supplier | supplier1@movement.com       | supplier123  |

---

## Troubleshooting

### "no such table: users"
The database hasn't been created. Run:
```bash
python seeds/seed.py
```

### "ModuleNotFoundError"
Make sure your virtual environment is activated and dependencies installed:
```bash
pip install -r requirements.txt
```

### Reset the database
Delete `freightflow.db` from the project root, then re-run the seed:
```bash
del freightflow.db        # Windows
rm freightflow.db         # Mac/Linux
python seeds/seed.py
```

---

## Project structure

```
ffn_full/
├── run.py                      ← Start the app
├── config.py                   ← Configuration
├── .env                        ← Environment variables
├── requirements.txt
├── freightflow.db              ← SQLite DB (created by seed)
├── app/
│   ├── models/                 ← SQLAlchemy models (14 tables)
│   ├── routes/                 ← Flask blueprints
│   │   ├── auth.py             ← Login, register, logout
│   │   ├── shipper.py          ← Shipper portal
│   │   ├── supplier.py         ← Supplier portal
│   │   ├── admin.py            ← Admin portal
│   │   ├── driver.py           ← Driver portal
│   │   └── public.py           ← Landing, tracking, API
│   ├── services/
│   │   ├── ai_engine.py        ← AI matching + health score
│   │   ├── v19_adapter.py      ← DB → template data adapter
│   │   ├── notifications.py
│   │   └── audit.py
│   ├── pipelines/
│   │   └── tasks.py            ← ETL pipelines (requires Redis)
│   └── templates/              ← v19 UI templates (85 files)
└── seeds/seed.py               ← Database seeder
```

---

## Optional: Background pipelines (requires Redis)

If you have Redis running:
```bash
# Worker
celery -A run.celery worker --loglevel=info

# Beat scheduler
celery -A run.celery beat --loglevel=info
```

Pipelines run automatically:
- Supplier score recalculation (hourly)
- Health score refresh (every 6h)
- Risk flagging (every 30min)
- Quote expiry (daily midnight)
- Daily platform summary (07:00)

---

## Deploying to Render (free tier)

### Prerequisites
- A [GitHub](https://github.com) account
- A [Render](https://render.com) account (free)

---

### Step 1 — Push to GitHub

```bash
# From inside the ffn_full/ folder
git init
git add .
git commit -m "FreightFlow Nexus v19 — initial commit"

# Create a new repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/freightflow-nexus.git
git branch -M main
git push -u origin main
```

---

### Step 2 — Create a Web Service on Render

1. Go to [dashboard.render.com](https://dashboard.render.com) → **New → Web Service**
2. Connect your GitHub repo
3. Fill in the settings:

| Field | Value |
|---|---|
| **Name** | `freightflow-nexus` |
| **Root Directory** | *(leave blank — repo root is ffn_full/)* |
| **Runtime** | `Python 3` |
| **Build Command** | `chmod +x build.sh && ./build.sh` |
| **Start Command** | `gunicorn run:app --workers 2 --bind 0.0.0.0:$PORT --timeout 120` |
| **Instance Type** | `Free` |

---

### Step 3 — Set environment variables

In **Render → Your Service → Environment**, add:

| Key | Value |
|---|---|
| `FLASK_ENV` | `production` |
| `SECRET_KEY` | *(click "Generate" for a random value)* |
| `PLATFORM_FEE_PCT` | `26.7` |

Leave Celery/Redis/Mail vars out — the app works without them for demo purposes.

---

### Step 4 — Deploy

Click **Create Web Service**. Render will:
1. Install dependencies (`pip install -r requirements.txt`)
2. Seed the database with demo data (`python seeds/seed.py`)
3. Start gunicorn

Your app will be live at `https://freightflow-nexus.onrender.com` (or similar).

---

### Demo credentials (after seed)

| Role | Email | Password |
|---|---|---|
| Admin | admin@movement.com | admin1234 |
| Shipper | shipper1@movement.com | shipper123 |
| Supplier | supplier1@movement.com | supplier123 |

---

### Important notes for Render free tier

- **SQLite lives on ephemeral disk** — the database resets on every new deploy or when the instance spins down and restarts. This is fine for demos. For production, swap `DATABASE_URL` for a Render PostgreSQL instance (free tier available).
- **Free tier spins down after 15 min of inactivity** — the first request after sleep takes ~30 seconds to wake up. Normal for demos.
- **No persistent file uploads** — evidence files uploaded via the complaints form are stored in `app/static/complaint_evidence/` which is also ephemeral. For production, use Cloudinary or S3.

---

### Upgrading to PostgreSQL (optional)

1. In Render, create a **PostgreSQL** database (free tier)
2. Copy the **Internal Database URL**
3. Add it as an environment variable: `DATABASE_URL` = `postgresql://...`
4. Install psycopg2: add `psycopg2-binary>=2.9` to `requirements.txt`
5. Redeploy — Flask-SQLAlchemy will switch automatically

