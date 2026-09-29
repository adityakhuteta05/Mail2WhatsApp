import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.config import settings
from app.database import init_db, SessionLocal
from app.routes import auth_router, gmail_router, webhook_router, health_router
from app.services.sync_service import SyncService
from app.utils.logging import logger

# Background scheduler task handle
_background_task = None


async def background_worker():
    """
    Periodic background loop for:
    1. Retrying failed emails in RETRY_WAIT (exponential backoff)
    2. Checking and renewing expiring Gmail mailbox watches (FR-02)
    """
    logger.info("Background worker started.")
    while True:
        try:
            db = SessionLocal()
            try:
                # 1. Retry pending emails
                retried = await SyncService.retry_pending_emails(db)
                if retried > 0:
                    logger.info(f"Background worker retried {retried} pending email(s).")

                # 2. Check expiring watches
                renewed = SyncService.check_and_renew_watches(db)
                if renewed > 0:
                    logger.info(f"Background worker renewed {renewed} Gmail watch(es).")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error in background worker iteration: {e}", exc_info=True)

        # Poll every 60 seconds
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info("Starting Mail2WhatsApp system...")
    init_db()

    # Launch background worker
    global _background_task
    _background_task = asyncio.create_task(background_worker())

    yield

    # --- Shutdown ---
    logger.info("Shutting down Mail2WhatsApp...")
    if _background_task:
        _background_task.cancel()
        try:
            await _background_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Mail2WhatsApp",
    description="Event-Driven Gmail to WhatsApp Email Forwarding Service (PRD 1.0)",
    version=__version__,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(webhook_router)
app.include_router(gmail_router)


@app.get("/", tags=["Root"])
def root_info():
    """Service information and status overview."""
    return {
        "service": "Mail2WhatsApp",
        "version": __version__,
        "status": "online",
        "environment": settings.APP_ENV,
        "docs_url": "/docs",
        "health_url": "/health",
    }


@app.exception_handler(Exception)
async def sanitized_exception_handler(request: Request, exc: Exception):
    """
    Catches unhandled exceptions, logs sanitized error details,
    and returns a safe JSON response without exposing tokens or internal state.
    """
    logger.error(f"Unhandled error processing {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred while processing the request."},
    )
