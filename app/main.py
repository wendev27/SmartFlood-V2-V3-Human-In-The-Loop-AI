"""
FastAPI application entry point.
Initializes the app, configures middleware, and sets up routes.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from contextlib import asynccontextmanager
import logging
import os
import sys
from dotenv import load_dotenv

from app.models.schemas import HealthCheckResponse
from app.routes.decision import router as decision_router
from app.database.mongodb import MongoDBConnection
from app.database.supabase import SupabaseConnection

# Load environment variables from .env if available
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting up AI Decision Service...")
    logger.info("Runtime Python %s", sys.version.split()[0])
    try:
        # Initialize database connections
        MongoDBConnection.connect()
        SupabaseConnection.connect()
        logger.info("Database connections initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database connections: {str(e)}")
        # Continue anyway - will fail on first request if DB is unavailable
    
    yield
    
    # Shutdown
    logger.info("Shutting down AI Decision Service...")
    try:
        MongoDBConnection.disconnect()
        logger.info("MongoDB connection closed")
    except Exception as e:
        logger.warning(f"Error closing MongoDB: {str(e)}")


# Create FastAPI app with lifespan context
app = FastAPI(
    title="AI Decision Service - Flood Disaster Management",
    description="Human-in-the-Loop AI system for flood relief allocation using Fuzzy Logic and AHP",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan
)


# Configure CORS — always include production origins; merge any extras from env var.
# IMPORTANT: CORS origins must be scheme+host only (never include paths like /relief).
_REQUIRED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://malabon-smartflood.vercel.app",
]
_extra_raw = os.getenv("ALLOWED_ORIGINS", "")
_extra_origins = [o.strip() for o in _extra_raw.split(",") if o.strip()]
ALLOWED_ORIGINS = list(dict.fromkeys(_REQUIRED_ORIGINS + _extra_origins))  # deduplicate, preserve order

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trusted hosts — include *.onrender.com by default so production deploys are not rejected.
# Set TRUSTED_HOSTS=* to disable host checking (local only).
_env = os.getenv("ENV", "production")
_default_trusted = "localhost,127.0.0.1,*.onrender.com"
if _env == "development":
    _default_trusted += ",testserver"
_trusted_raw = os.getenv("TRUSTED_HOSTS", _default_trusted).strip()
if _trusted_raw != "*":
    TRUSTED_HOSTS = [h.strip() for h in _trusted_raw.split(",") if h.strip()]
    if not TRUSTED_HOSTS:
        TRUSTED_HOSTS = ["localhost", "127.0.0.1", "*.onrender.com"]
    # Render sets RENDER=true; ensure the service hostname is accepted if .env omitted *.onrender.com
    if os.getenv("RENDER") == "true" and "*.onrender.com" not in TRUSTED_HOSTS:
        TRUSTED_HOSTS.append("*.onrender.com")
    if _env == "development" and "testserver" not in TRUSTED_HOSTS:
        TRUSTED_HOSTS.append("testserver")
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=TRUSTED_HOSTS
    )


# Add request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log requests at DEBUG to keep production logs readable (INFO for lifecycle and errors)."""
    logger.debug("%s %s", request.method, request.url.path)
    response = await call_next(request)
    logger.debug("status=%s path=%s", response.status_code, request.url.path)
    return response


# Include routes
app.include_router(decision_router, prefix="/api/v1", tags=["Decision"])


@app.get("/health", response_model=HealthCheckResponse, tags=["Health"])
async def health():
    """
    Liveness probe at the URL path most load balancers and docs expect.
    Does not require MongoDB or Supabase so the service stays reachable during DB outages.
    """
    return HealthCheckResponse(
        status="healthy",
        message="AI Decision Service is running",
    )


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint providing service information."""
    return {
        "service": "AI Decision Service",
        "version": "1.0.0",
        "description": "Human-in-the-Loop AI for flood disaster relief allocation",
        "endpoints": {
            "health": "/health",
            "decision": "/api/v1/decision",
            "docs": "/docs"
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 10000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting server on {host}:{port}")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=os.getenv("ENV", "production") == "development",
        log_level="info"
    )
