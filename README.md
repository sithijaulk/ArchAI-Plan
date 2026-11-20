# ArchAI-Plan

ArchAI-Plan is a web-based research platform for turning residential land and
building information into structured architectural design outputs. It combines
four spatial-design components with a shared project workflow, an administrative
website, and interactive 2D/3D previews.

Projects are exchanged between components through a shared **Master JSON**
document. Each component contributes its own output while preserving the
information produced by earlier steps.


## 👥 Team Members & Component

| Name                |Component|
|---------------------|----------------|
| **Udayawickrama K D S L N** *(Leader)* | ESAI-Engine |
| **Sithumini H Y K**  | GAB-Gen — Geo-Spatial AI Blueprint Generator |
| **Jayathilaka K M K M** | VSAI-Rectifier |
| **Prasad P A D H**    | ELIA-Engine — Eco-Spatial Landscape Intelligence |


---

## Project Components

| Component | Purpose | Current approach |
|---|---|---|
| **GAB-Gen — Geo-Spatial AI Blueprint Generator** | Reads survey/deed plans, derives land geometry, applies jurisdiction-specific building rules, and creates editable building/room layouts. | OpenCV and EasyOCR assist survey extraction. Geometry reconstruction, regulations, and space allocation are rule-based; users review extracted measurements before generation. |
| **VSAI-Rectifier** | Validates and rectifies spatial/floor-plan data and records the result in the Master JSON workflow. | Deterministic geometry and configured-rule checks. A CubiCasa5K segmentation path is available for floor-plan image analysis when the model checkpoint is configured. |
| **ESAI-Engine** | Generates interior furniture and asset layouts using room geometry, ergonomic constraints, functional relationships, and user preferences. | PyGAD evolutionary optimization with geometric and design constraints; supports alternative layouts, validation, and report generation. |
| **ELIA-Engine — Eco-Spatial Landscape Intelligence** | Plans exterior areas such as access, paths, vegetation, lighting, and outdoor amenities. | Production generation uses deterministic geometric planning and a versioned rules engine. Neural layout code and research material are optional/experimental and are not required for the default production planner. |

These components are at different stages and do not all use machine learning.
Generated plans are decision-support outputs and should be reviewed by qualified
professionals before construction or regulatory submission.

## Application Structure

```text
ArchAI-Plan/
├── backend/
│   ├── app/
│   │   ├── components/       # GAB-Gen, VSAI, ESAI, and ELIA engines
│   │   ├── ml/                # ML runtime, including CubiCasa5K
│   │   ├── models/            # SQLAlchemy database models
│   │   ├── routers/           # FastAPI API endpoints
│   │   ├── schemas/           # API request and response schemas
│   │   ├── services/          # Shared project, geometry, and domain services
│   │   └── utils/             # Backend utilities
│   ├── alembic/               # Database migrations
│   ├── scripts/               # Backend administration scripts
│   ├── tests/                 # Backend tests
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── app/               # Next.js routes and pages
│       ├── components/        # Shared UI, workflow, and visualization
│       ├── features/          # Feature-specific frontend modules
│       ├── lib/               # API clients and shared helpers
│       ├── store/             # Client state
│       └── types/             # TypeScript types
├── shared/
│   ├── vsi-bd/                # Shared VSAI/project JSON data
│   └── vsai-bd/               # Shared VSAI project JSON data
├── training/                  # Model training code and research artifacts
├── docs/                      # Component contracts, runbooks, and research
└── docker-compose.yml         # Frontend, backend, and PostgreSQL services
```

## Languages, Frameworks, and Technologies

### Frontend

- **TypeScript, JavaScript, HTML, and CSS**
- **Next.js 14** (App Router) and **React 18**
- **Tailwind CSS** and Radix UI-based components
- **Three.js**, React Three Fiber, and Drei for 3D views
- **Zustand** for client-side state
- **Axios**, React Hook Form, and Zod for API requests and form validation
- **Framer Motion** for animations; **jsPDF** and html2canvas for exports

### Backend

- **Python 3.11+**, **FastAPI**, and **Uvicorn**
- **SQLAlchemy** and **Alembic**
- **PostgreSQL** (PostgreSQL 16 is used by the provided Docker Compose setup)
- **Pydantic** for settings and data validation
- **JWT** authentication and Argon2 password hashing
- **Shapely, NumPy, SciPy, NetworkX, Pillow, and OpenCV** for spatial and image processing
- **PyTorch, torchvision, EasyOCR, scikit-learn, and XGBoost** for ML-related runtime and research work
- **PyMuPDF, ReportLab, and FPDF2** for document and report processing

### Development and Deployment

- **Node.js 18+** and npm
- **Docker Compose** for the frontend, API, and PostgreSQL services
- **pytest** and **pytest-asyncio** for backend tests
- **TypeScript** and ESLint for frontend validation

## AI and Machine-Learning Details

| Area | Model/technique | Runtime status |
|---|---|---|
| Survey-plan extraction (GAB-Gen) | EasyOCR text recognition with OpenCV image preprocessing and geometry detection. | Available as an extraction provider; extracted survey details are reviewed and confirmed as part of the workflow. |
| Blueprint generation (GAB-Gen) | Regulatory rules, geometric reconstruction, and deterministic space allocation. XGBoost training/evaluation materials are also present. | The deterministic generator is the active baseline; the XGBoost model is research/experimental, not the production layout generator. |
| Floor-plan segmentation (VSAI) | CubiCasa5K multi-task segmentation implemented with PyTorch; predicts room and icon classes from floor-plan images. | The segmentation path requires a compatible checkpoint configured with `CUBICASA_WEIGHTS_PATH`. VSAI's normal rectification and configured-rule checks are deterministic and do not claim complete Vastu compliance. |
| Interior layout (ESAI) | PyGAD genetic algorithm searches candidate furniture layouts, scored against spatial, ergonomic, functional, and preference constraints. | Used by the ESAI generation endpoint; results can be validated and saved through the project workflow. |
| Exterior layout (ELIA) | Geometry planners, pathfinding, solar/environmental calculations, and explicit versioned rules. A compact UNet-style layout model and research training/evaluation material are also present. | The default production generation mode is the deterministic rules planner. Neural layout inference is optional and is not required for standard generation. |

ML outputs and automated rules do not replace professional architectural,
engineering, botanical, or regulatory review.

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.11+
- PostgreSQL 14+ (or Docker with Docker Compose)

### Run with Docker Compose

1. Copy `.env.docker.example` to `.env` and set a secure `JWT_SECRET_KEY` and
   PostgreSQL credentials.
2. Start the services from the repository root:

   ```bash
   docker compose up --build
   ```

3. Open the frontend at `http://localhost:3000`. The API is available at
   `http://localhost:8000`, with interactive documentation at
   `http://localhost:8000/docs`.

### Run Services Locally

Start PostgreSQL and create the `archai_plan` database, then configure the
database connection and a strong `JWT_SECRET_KEY` in `backend/.env`. Use
`backend/.env.example` as a reference and set `DB_HOST`, `DB_PORT`, `DB_NAME`,
`DB_USER`, and `DB_PASSWORD` for your local environment.

```bash
# Terminal 1: backend
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

```bash
# Terminal 2: frontend
cd frontend
npm install
cp .env.example .env.local         # Windows: copy .env.example .env.local
npm run dev
```

Set `NEXT_PUBLIC_API_URL=http://localhost:8000/api` in `frontend/.env.local`.
Open `http://localhost:3000` for the application.

The CubiCasa5K image-segmentation path additionally needs model weights accessible
to the backend and configured through `CUBICASA_WEIGHTS_PATH`. Do not commit
model checkpoints, credentials, or local environment files.

## Main Routes

| Route | Description |
|---|---|
| `/` | Project home |
| `/gallery` | Published research projects |
| `/features/gab-gen` | Survey and blueprint workflow |
| `/features/vsai-rectifier` | VSAI rectification workflow |
| `/features/esai-engine` | Interior-design workflow |
| `/features/elia-engine` | Exterior and landscape workflow |
| `/start` | Start or create a project |
| `/about`, `/contact` | Project information and contact form |
| `/admin` | Administrative dashboard and content management |

The backend API is rooted at `/api`. Use `/docs` for the complete, current
endpoint list and schemas.

## Shared Project Data

Components exchange project state through the Master JSON document. Its
high-level sections include:

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
    "gab_gen": {},
    "vsai_rectifier": {},
    "esai_engine": {},
    "elia_engine": {}
  }
}
```

The exact schema evolves with the component contracts. Components should enrich
their own section without discarding unrelated project data.

## Validation

Run backend tests from `backend/`:

```bash
python -m pytest
```

Run frontend checks from `frontend/`:

```bash
npx tsc --noEmit
npm run lint
npm run build
```

Database-backed tests require a configured PostgreSQL database and applied
migrations.

## Documentation

Component-specific contracts, operating guidance, evaluation material, and
research notes are available under [`docs/`](./docs/), alongside component
documentation in `backend/app/components/`.
