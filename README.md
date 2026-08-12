# Event Pass System

A Flask-based web application for generating, managing, and verifying digital event passes with QR codes. Built for ticketed events, it handles pass generation, sponsor/branding management, and entry scanning — with pass images rendered server-side and stored on AWS S3, and all records kept in MongoDB.

## Features

- **Pass Generation** — Create branded event passes with a unique serial number, sequence number, and embedded QR code.
- **QR Code Verification** — Scan passes via camera (using `html5-qrcode`) or manual serial number entry to validate entry at the door.
- **Duplicate-Entry Protection** — Passes are marked as scanned on verification, preventing re-use.
- **Sponsor Management** — Upload, activate/deactivate, and delete sponsor logos, which are rendered onto generated passes.
- **"Powered By" Branding** — Configure a brand name/logo shown in the corner of every pass.
- **Pass Gallery** — Browse all generated passes with pagination.
- **Live Statistics** — Dashboard showing total passes, scanned/pending counts, attendance rate, and a breakdown by ticket type.
- **Secure File Storage** — Pass images and logos are stored privately in S3 and served via time-limited presigned URLs.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Flask 3 |
| Database | MongoDB (via PyMongo) |
| File Storage | AWS S3 (via boto3) |
| Image Generation | Pillow (PIL) |
| QR Codes | `qrcode` |
| QR Scanning | `html5-qrcode` (client-side JS) |
| Rate Limiting | Flask-Limiter |
| WSGI Server | Gunicorn |

## Project Structure

```
.
├── app.py                     # App factory, blueprint registration, security headers
├── config.py                  # Environment-driven configuration
├── requirements.txt
│
├── routes/
│   ├── main_routes.py          # Landing page, stats API
│   ├── pass_routes.py          # Pass generation, listing, download
│   ├── scan_routes.py          # Verification & scan history
│   ├── sponsor_routes.py       # Sponsor CRUD
│   └── powered_by_routes.py    # "Powered by" branding CRUD
│
├── services/
│   ├── database.py             # MongoDB singleton connection & indexes
│   ├── pass_service.py         # Pass creation, retrieval, stats aggregation
│   ├── scan_service.py         # Verify/scan logic
│   ├── sponsor_service.py      # Sponsor logo management
│   ├── powered_by_service.py   # Branding logo management
│   └── s3_service.py           # S3 upload/download/presigned URLs
│
├── utils/
│   ├── pass_designer.py        # Renders the pass image (cosmic ticket design)
│   └── qr_generator.py
│
└── templates/
    ├── index.html               # Landing page + live stats
    ├── generate.html            # Pass generation form
    ├── view_passes.html         # Paginated pass gallery
    ├── scan.html                # QR scanner / manual verification
    ├── sponsor.html             # Sponsor management UI
    └── powered_by.html          # Branding management UI
```

## Getting Started

### Prerequisites

- Python 3.9+
- A running MongoDB instance
- An AWS account with an S3 bucket and IAM credentials

### Installation

```bash
git clone (https://github.com/VarunSinha123/holievent.git)
cd event-pass-system
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
SECRET_KEY=your-secret-key
FLASK_ENV=development

MONGODB_URI=mongodb://localhost:27017/
DATABASE_NAME=event_pass_system

AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-north-1
S3_BUCKET_NAME=your-bucket-name
```

### Running the App

```bash
python app.py
```

The app will be available at `http://localhost:5000`.

For production, use Gunicorn:

```bash
gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app()"
```

## API Overview

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/stats` | Overall pass/scan statistics |
| POST | `/pass/api/generate` | Generate a new pass |
| GET | `/pass/api/list` | List passes (paginated) |
| GET | `/pass/api/get/<serial_number>` | Get a single pass |
| GET | `/pass/download/<serial_number>` | Download a pass image |
| POST | `/scan/api/verify` | Verify and scan a pass |
| GET | `/scan/api/history` | Scan history (paginated) |
| POST | `/sponsor/api/add` | Add a sponsor |
| GET | `/sponsor/api/list` | List sponsors |
| POST | `/sponsor/api/toggle/<sponsor_id>` | Activate/deactivate a sponsor |
| DELETE | `/sponsor/api/delete/<sponsor_id>` | Delete a sponsor |
| GET | `/powered-by/api/get` | Get active branding |
| POST | `/powered-by/api/update` | Update branding |
| POST | `/powered-by/api/add` | Add new branding entry |
| GET | `/powered-by/api/list` | List all branding entries |
| POST | `/powered-by/api/toggle/<id>` | Activate/deactivate branding |
| DELETE | `/powered-by/api/delete/<id>` | Delete branding entry |

## Security Notes

- S3 objects are stored as **private**; access is granted only through short-lived presigned URLs.
- Security headers (CSP, X-Frame-Options, X-Content-Type-Options, HSTS in production) are applied to every response.
- File uploads are restricted to PNG/JPG/JPEG and capped at 16MB.

## License

Add your license of choice here.
