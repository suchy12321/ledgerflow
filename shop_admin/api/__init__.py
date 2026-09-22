"""Shop Admin HTTP routers."""

from .auth import router as auth_router
from .customers import router as customers_router
from .dashboard import router as dashboard_router
from .email_webhook import router as email_webhook_router
from .inbox import router as inbox_router
from .messenger_webhook import router as messenger_webhook_router
from .orders import router as orders_router
from .products import router as products_router
from .warehouses import router as warehouses_router

__all__ = [
    "auth_router",
    "customers_router",
    "dashboard_router",
    "email_webhook_router",
    "inbox_router",
    "messenger_webhook_router",
    "orders_router",
    "products_router",
    "warehouses_router",
]
