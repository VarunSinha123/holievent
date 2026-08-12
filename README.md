<div align="center">

# 🎫 Elite Event Pass System

**A role-based Flask platform for issuing, distributing, and scanning digital event passes — with QR-coded tickets, bulk provisioning, live entry scanning, and full audit logging.**

[![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![MongoDB](https://img.shields.io/badge/MongoDB-Atlas-47A248?logo=mongodb&logoColor=white)](https://www.mongodb.com/atlas)
[![AWS S3](https://img.shields.io/badge/AWS-S3-FF9900?logo=amazons3&logoColor=white)](https://aws.amazon.com/s3/)
[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Add%20Yours-lightgrey)](#license)

</div>

---

## Overview

Elite Event Pass System is a multi-tenant event ticketing backend built with **Flask**, **MongoDB**, and **AWS S3**. It supports four distinct user roles — attendees, on-site security staff, event admins, and a super admin — each with their own dashboard and permission boundary, enforced through Flask-Login session roles and route-level decorators.

Every pass is rendered server-side as a branded PNG with an embedded QR code, uploaded to a private S3 bucket, and served back through short-lived presigned URLs. Entry is verified in real time via camera-based QR scanning, with double-scan protection and live per-bouncer/per-event statistics.

---

## ✨ Features

### 🔐 Authentication & Access Control
- Role-based login (`user`, `bouncer`, `admin`, `super_admin`) with a single unified login screen
- Brute-force protection — accounts auto-lock after 5 failed attempts, with a 10-minute cooldown
- Scrypt password hashing, secure session cookies, and CSP/HSTS security headers on every response
- Super Admin can manually unlock accounts and audit every login attempt

### 🎟️ Pass & Ticketing
- Single or batch pass generation, with attendee name, ticket tier, and event auto-fill
- Vibrant, festival-styled pass image rendering via Pillow (`utils/pass_designer.py`)
- **Bulk QR Vault** — provision up to 500 standalone QR codes per batch, exportable as print-ready PDF sheets or PNG grids (individually or zipped in batches)
- Passes and QR codes stored privately on S3; access only via time-limited presigned URLs

### 📷 Live Entry Scanning
- Camera-based QR scanning (`html5-qrcode`) with audio feedback and duplicate-entry protection
- Real-time event-wide and per-bouncer scan statistics
- Bouncers self-select their gate/event assignment; admins get master access to all active events

### 🛂 Staff & Event Management
- Admins onboard and deploy bouncers, assign them to events, and monitor deployments in real time
- Full event CRUD with multiple ticket tiers, pricing, and availability per event
- Global "kill switch" to activate/deactivate every event at once (Super Admin)

### 📊 Dashboards & Audit Trail
- Role-specific dashboards (User, Bouncer, Admin, Super Admin) with live stats and reload controls
- Centralized audit log for logins, lockouts, unlocks, event changes, staff changes, and more
- Terminal-styled security audit console with locked-account alerts and filterable log streams

---

## 🧱 Tech Stack

| Layer | Technology |
|---|---|
| Backend framework | Flask 3, Flask-Login |
| Database | MongoDB (via PyMongo), MongoDB Atlas-ready |
| Object storage | AWS S3 (via boto3), private buckets + presigned URLs |
| Image / QR generation | Pillow, `qrcode` |
| PDF / batch export | ReportLab |
| QR scanning (client) | `html5-qrcode` |
| Frontend | Server-rendered Jinja templates, vanilla JS, hand-rolled CSS / Tailwind (per page) |
| WSGI server | Gunicorn |
| Auth | Flask-Login sessions, Werkzeug scrypt password hashing |

---

## 📁 Project Structure

```
.
├── app.py                      # App factory, blueprint registration, security headers
├── config.py                   # Environment-driven configuration
├── requirements.txt
│
├── routes/
│   ├── main_routes.py           # Landing page, global stats
│   ├── auth_routes.py           # Login, register, logout, profile, password change
│   ├── user_routes.py           # Attendee dashboard & purchase APIs
│   ├── admin_routes.py          # Admin dashboard, user & bouncer management
│   ├── super_admin_routes.py    # System-wide stats, admin/bouncer control, audit logs
│   ├── bouncer_routes.py        # Bouncer dashboard, scanning, staff assignment
│   ├── scan_routes.py           # Scanner APIs & stats (bouncer-scoped)
│   ├── event_routes.py          # Event & ticket-type CRUD
│   ├── pass_routes.py           # Single pass generation, listing, download
│   └── bulk_qr_routes.py        # Bulk QR generation & batch export (PDF/PNG/ZIP)
│
├── services/
│   ├── database.py              # MongoDB singleton connection, indexes, collections
│   ├── auth_service.py          # Registration, login, brute-force protection
│   ├── audit_service.py         # Centralized audit logging
│   ├── event_service.py         # Event & ticket-type business logic
│   ├── bouncer_service.py       # Bouncer accounts & event assignments
│   ├── pass_service.py          # Pass creation, QR generation, scan logic
│   ├── bulk_qr_service.py       # Bulk QR generation, PDF/PNG sheet export
│   ├── scan_service.py          # Entry verification & double-scan protection
│   └── s3_service.py            # S3 upload, presigned URL generation
│
├── models/
│   └── user.py                  # Flask-Login User model
│
├── utils/
│   └── pass_designer.py         # Renders the branded pass image
│
└── templates/                   # Role-specific dashboards, login/register, scanner UI
```

---

## 👥 Roles & Access

| Role | Can do |
|---|---|
| **User** | Browse events, purchase passes, view their own tickets & profile |
| **Bouncer** | Select assigned event/gate, scan passes, view own & event scan stats |
| **Admin** | Manage events & ticket tiers, onboard/deploy bouncers, manage users, generate passes, bulk QR |
| **Super Admin** | Everything Admin can do, plus: manage other admins, global event kill-switch, unlock accounts, full audit log access |

Access is enforced both at the Flask route layer (`@login_required` + role decorators) and reflected in the UI (role-specific dashboards and navigation).

---

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- A MongoDB instance (local or [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register))
- An AWS account with an S3 bucket and a scoped IAM user/role

### Installation

```bash
git clone <your-repo-url>
cd event-pass-system
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
SECRET_KEY=replace-with-a-long-random-string
FLASK_ENV=development

MONGODB_URI=mongodb://localhost:27017/
DATABASE_NAME=event_pass_system

AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=eu-north-1
S3_BUCKET_NAME=your-bucket-name
```

> Generate a strong secret key with: `python3 -c "import secrets; print(secrets.token_hex(32))"`

### Run locally

```bash
python app.py
```

The app will be available at `http://localhost:5000`.

For production, run behind Gunicorn (and a reverse proxy like Nginx):

```bash
gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app()"
```

---

## 🔌 Key API Routes

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/api/register` | Register a new attendee account |
| `POST` | `/auth/api/login` | Role-verified login |
| `POST` | `/auth/api/logout` | End session |
| `GET` | `/event/api/list` | List events (admin) |
| `POST` | `/event/api/create` | Create event with ticket tiers |
| `POST` | `/pass/api/generate` | Generate a single branded pass + QR |
| `POST` | `/bulk-qr/api/generate` | Bulk-generate standalone QR codes |
| `GET` | `/bulk-qr/api/download-pdf` | Export unused QR codes as a print-ready PDF |
| `POST` | `/bouncer/api/scan` | Verify & scan a pass at the door |
| `GET` | `/bouncer/api/stats` | Live scan stats (bouncer + event-wide) |
| `GET` | `/super-admin/api/audit-logs` | Query the system audit trail |
| `POST` | `/super-admin/api/unlock-account/<user_id>` | Manually unlock a locked account |

---

## 🛡️ Security Notes

- Passwords are hashed with **scrypt** (never stored in plaintext)
- Accounts auto-lock after 5 failed logins for 10 minutes, with full audit logging of lockouts/unlocks
- S3 objects are private; all access goes through short-lived **presigned URLs**
- Security headers (`X-Frame-Options`, `X-Content-Type-Options`, CSP, HSTS in production) are applied to every response
- Session cookies are `HttpOnly` + `SameSite=Lax`, and marked `Secure` automatically when `FLASK_ENV=production`
- File uploads are size-capped and extension-restricted

---

## 🗺️ Roadmap Ideas

- [ ] Payment gateway integration for self-serve ticket purchase
- [ ] Email/SMS delivery of generated passes
- [ ] Per-event analytics dashboard (sales, attendance trends over time)
- [ ] Automated tests & CI pipeline

---

## 📄 License

Add your license of choice here (MIT, Apache 2.0, etc.).
