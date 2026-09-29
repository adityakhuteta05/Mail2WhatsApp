from app.routes.auth import router as auth_router
from app.routes.gmail import router as gmail_router
from app.routes.webhook import router as webhook_router
from app.routes.health import router as health_router

__all__ = [
    "auth_router",
    "gmail_router",
    "webhook_router",
    "health_router",
]
