import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, engine
from .routers import auth, gallery, admin_gallery, contact, projects, admin, settings as settings_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure upload directories exist
    logger.info(f"Starting {settings.app_name} backend...")
    os.makedirs(os.path.join(settings.upload_dir, "gallery"), exist_ok=True)
    logger.info("Upload directories initialized.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="ArchAI-Plan API",
    description="Multi-Agent Spatial AI Architecture for Residential Design",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS — must specify exact origin when using credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
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
app.include_router(projects.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}
