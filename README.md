# ArchAI-Plan

ArchAI-Plan is a research platform for transforming residential spatial information into structured architectural outputs. The shared `main` branch contains the public website, administrative CMS, MySQL persistence, authentication, project workflow, visualization infrastructure, and integration shells for four future research engines.

The AI engines are intentionally not implemented in `main`. Their API routes return HTTP `501` until the corresponding feature branches provide the engine integrations.

## Architecture

```
ArchAI-Plan/
├── frontend/          # Next.js + React + TypeScript + Three.js
├── backend/           # Python FastAPI + SQLAlchemy + MySQL
├── shared/            # Master JSON schema contract
├── training/          # Future AI model training data
└── docs/              # Project documentation
```

The application is split into a Next.js frontend and a FastAPI backend. MySQL is the only runtime database. Zustand holds UI/cache state; permanent project and Master JSON state is stored through the backend.

## Technology Stack

### Frontend
- **Next.js 14** (App Router), React, TypeScript
- **Tailwind CSS**, shadcn/ui components
- **Three.js** + @react-three/fiber + @react-three/drei (3D visualization)
- **Framer Motion** (animations), Lucide React (icons)
- **Zustand** (state), Axios (API calls), React Hook Form + Zod (validation)
- **html2canvas + jsPDF** (export)

### Backend
- **Python 3.11+**, FastAPI, Uvicorn
- **SQLAlchemy 2.x** ORM, Alembic (migrations)
- **MySQL** with utf8mb4 charset
- **JWT** authentication via HttpOnly cookies
- **Argon2** password hashing (via pwdlib)
- **Pillow** (image processing), python-multipart (file uploads)

### Database

- MySQL 8 with `utf8mb4` / `utf8mb4_unicode_ci`
- SQLAlchemy 2.x and Alembic
- PyMySQL driver
- No local database fallback

---

## Requirements

- Node.js 18+
- Python 3.11+
- MySQL 8.0+

---

## MySQL Setup

```sql
-- In MySQL shell or Workbench
CREATE DATABASE archai_plan
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

---

## Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate (macOS/Linux)
source .venv/bin/activate

# Activate (Windows)
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env             # Windows
# cp .env.example .env             # macOS/Linux
# Edit .env — set DATABASE_URL with your MySQL credentials and a strong JWT_SECRET_KEY

# Run database migrations
alembic upgrade head

# Create the first admin account
python scripts/create_admin.py

# Start backend server
uvicorn app.main:app --reload --port 8000
```

Backend URLs:
- API: http://localhost:8000/api
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/api/health

---

## Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
cp .env.example .env.local
# Verify NEXT_PUBLIC_API_URL=http://localhost:8000/api

# Start development server
npm run dev
```

Frontend URL: http://localhost:3000

---

## Public Routes

| Route | Page |
|-------|------|
| `/` | Home |
| `/gallery` | Research Gallery |
| `/gallery/[slug]` | Gallery Detail |
| `/features` | Features Overview |
| `/features/gab-gen` | GAB-Gen Workflow |
| `/features/vsai-rectifier` | VSAI Workflow |
| `/features/esai-engine` | ESAI Workflow |
| `/features/elia-engine` | ELIA Workflow |
| `/about` | About ArchAI-Plan |
| `/contact` | Contact Us |
| `/start` | Start / Create Project |

## Admin Routes

| Route | Page |
|-------|------|
| `/admin/login` | Admin Login |
| `/admin` | Dashboard |
| `/admin/gallery` | Gallery Management |
| `/admin/gallery/new` | New Project |
| `/admin/gallery/[id]/edit` | Edit Project |
| `/admin/messages` | Contact Messages |
| `/admin/settings` | Website Settings |

---

## REST API Endpoints

### Authentication
- `POST /api/auth/login` — Admin login (sets HttpOnly cookie)
- `POST /api/auth/refresh` — Rotate the refresh cookie and issue a new access cookie
- `POST /api/auth/logout` — Logout (clears cookies)
- `GET /api/auth/me` — Current authenticated user

### Public Gallery
- `GET /api/gallery` — Published projects (paginated, filterable)
- `GET /api/gallery/{slug}` — Single published project

### Admin Gallery
- `GET /api/admin/gallery` — All projects
- `POST /api/admin/gallery` — Create project
- `GET /api/admin/gallery/{id}` — Get project
- `PUT /api/admin/gallery/{id}` — Update project
- `DELETE /api/admin/gallery/{id}` — Delete project + files
- `POST /api/admin/gallery/{id}/images` — Upload image (cover or gallery)
- `DELETE /api/admin/gallery/{id}/images/{imageId}` — Delete image
- `PATCH /api/admin/gallery/{id}/publish` — Publish
- `PATCH /api/admin/gallery/{id}/unpublish` — Unpublish

### Contact
- `POST /api/contact` — Submit contact form
- `GET /api/admin/messages` — Admin: list messages
- `PATCH /api/admin/messages/{id}/read` — Mark as read
- `PATCH /api/admin/messages/{id}/unread` — Mark as unread
- `DELETE /api/admin/messages/{id}` — Delete message

### Research Projects
- `POST /api/projects` — Create project
- `GET /api/projects` — List projects
- `GET /api/projects/{id}` — Get project
- `PUT /api/projects/{id}` — Update project
- `DELETE /api/projects/{id}` — Delete project
- `GET /api/projects/{id}/master-json` — Get Master JSON
- `POST /api/projects/{id}/skip/{component}` — Skip component

### Future AI Component Stubs (HTTP 501)
- `POST /api/projects/{id}/gab-gen/run`
- `POST /api/projects/{id}/vsai-rectifier/run`
- `POST /api/projects/{id}/esai-engine/run`
- `POST /api/projects/{id}/elia-engine/run`

Each pending engine response is controlled and explicit:

```json
{ "detail": "Component engine integration pending" }
```

### Admin & Settings
- `GET /api/admin/stats` — Dashboard statistics
- `GET /api/settings` — Site settings
- `PUT /api/settings` — Update settings (admin)

---

## Git Branch Strategy

| Branch | Ownership |
|--------|-----------|
| `main` | Shared platform, UI, DB, Auth, Gallery, CMS, Workflow shells |
| `feature/gab-gen` | `backend/app/components/gab_gen/`, `frontend/src/features/gab-gen/` |
| `feature/vsai-rectifier` | `backend/app/components/vsai_rectifier/`, `frontend/src/features/vsai/` |
| `feature/esai-engine` | `backend/app/components/esai_engine/`, `frontend/src/features/esai/` |
| `feature/elia-engine` | `backend/app/components/elia_engine/`, `frontend/src/features/elia/` |

---

## Master JSON Contract

The centralized data contract propagated through all four AI components:

```json
{
  "project_id": "",
  "project_name": "",
  "land_info": {},
  "buildable_footprint": {},
  "floor_plan": {},
  "structural_rectification": {},
  "interior_layout": {},
  "exterior_landscape": {},
  "processing": {
    "gab_gen": { "status": "pending" },
    "vsai_rectifier": { "status": "pending" },
    "esai_engine": { "status": "pending" },
    "elia_engine": { "status": "pending" }
  }
}
```

**Rule:** Each later component enriches the document without deleting prior component output.

---

## Gallery Media

Files are stored at: `backend/app/uploads/gallery/{project-id}/cover/` and `.../images/`

The database stores the **relative path** only. The backend serves files via FastAPI `StaticFiles` at `/uploads/*`.

Uploads are validated by extension, MIME type, size, and Pillow image verification. Files receive UUID-based names and are served only from the configured public uploads directory.

---

## Security Notes

- Passwords hashed with **Argon2** (via `pwdlib`)
- JWT stored in **HttpOnly cookies** (not localStorage)
- CORS locked to `FRONTEND_URL` — no wildcard origin with credentials
- All admin endpoints enforce `require_admin()` dependency server-side
- Image uploads: MIME validation + extension check + UUID filenames + path traversal prevention
- No raw SQL — all queries via SQLAlchemy ORM

## Environment Files

Copy `backend/.env.example` to `backend/.env` and set a real MySQL password and long random JWT secret. Copy `frontend/.env.example` to `frontend/.env.local`. Database credentials must never be placed in frontend variables or committed files.

## Master JSON Workflow

Creating a project writes the initial Master JSON to MySQL. The frontend then loads the response into Zustand. Component skips update only the relevant processing status and preserve all other layers. JSON uploads are validated before being persisted as a new project.

## Branch Strategy

The existing feature branches own their isolated integration surfaces:

- `feature/gab-gen` -> GAB-Gen
- `feature/vsai-rectifier` -> VSAI-Rectifier
- `feature/esai-engine` -> ESAI-Engine
- `feature/elia-engine` -> ELIA-Engine

Do not merge engine implementations into `main` until their contracts and tests are ready.

## Validation

Backend syntax can be checked with:

```bash
python -m compileall app alembic scripts
```

Frontend checks:

```bash
npm run lint
npx tsc --noEmit
npm run build
```

Run database-backed integration checks only after MySQL is available and `alembic upgrade head` has completed.

---

*ArchAI-Plan Research Initiative — v2.0 (FastAPI + MySQL architecture)*
