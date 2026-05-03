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
from dotenv import load_dotenv

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


# Configure CORS - adjust origins for production
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add security middleware for trusted hosts
TRUSTED_HOSTS = os.getenv("TRUSTED_HOSTS", "localhost,127.0.0.1").split(",")
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=TRUSTED_HOSTS
)


# Add request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests."""
    logger.info(f"{request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"Status code: {response.status_code}")
    return response


# Include routes
app.include_router(decision_router, prefix="/api/v1", tags=["Decision"])


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
