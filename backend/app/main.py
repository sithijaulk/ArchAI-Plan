import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, engine
from .routers import auth, gallery, admin_gallery, contact, projects, admin, about, settings as settings_router, elia, gab_gen, vsai_rectifier

import ssl
try:
    import certifi
    ca_bundle = certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", ca_bundle)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)
    ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=ca_bundle)
except Exception:
    pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure upload directories exist and create PostgreSQL tables
    logger.info(f"Starting {settings.app_name} backend on PostgreSQL...")
    os.makedirs(os.path.join(settings.upload_dir, "gallery"), exist_ok=True)
    os.makedirs(os.path.join(settings.upload_dir, "research"), exist_ok=True)
    os.makedirs(os.path.join(settings.upload_dir, "team"), exist_ok=True)
    logger.info("Upload directories initialized.")
    # Auto-create tables in PostgreSQL schema if database is reachable
    try:
        # Import all models to ensure they register with Base.metadata
        from .models import user, project, component_run, gallery_image, gallery_project, contact_message, site_setting, research_document, team_member, esai
        Base.metadata.create_all(bind=engine)
        logger.info("PostgreSQL database tables verified and created successfully.")
    except Exception as e:
        logger.warning(f"Could not connect to PostgreSQL at startup ({e}). Continuing with app initialization.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="ArchAI-Plan API",
    description="Multi-Agent Spatial AI Architecture for Residential Design (PostgreSQL Edition)",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS — allow development frontend ports including localhost:3002
allowed_origins = list({
    settings.frontend_url,
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://localhost:3003",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:3002",
    "http://127.0.0.1:3003",
})

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded media files
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

# Include all routers
app.include_router(auth.router, prefix="/api")
app.include_router(gallery.router, prefix="/api")
app.include_router(admin_gallery.router, prefix="/api")
app.include_router(contact.router, prefix="/api")
app.include_router(contact.admin_router, prefix="/api")
app.include_router(vsai_rectifier.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(elia.router, prefix="/api")
app.include_router(gab_gen.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(about.router, prefix="/api")
app.include_router(about.admin_router, prefix="/api")

# Add CubiCasa5K Research Router
from .routers import research_cubicasa
app.include_router(research_cubicasa.router, prefix="/api")

# Add ESAI Routers
from .routers import esai
app.include_router(esai.project_router)
app.include_router(esai.global_router)


@app.get("/api/health")
def health_check():
    db_connected = False
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_connected = True
    except Exception:
        db_connected = False

    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "database": {
            "configured_dialect": "postgresql",
            "connected": db_connected
        }
    }
