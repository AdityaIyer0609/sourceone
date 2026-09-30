from fastapi import APIRouter

from app.api.v1 import (
    admin_integrations, admin_pricing, admin_products, admin_users, approvals, auth, benchmarks, dashboard, freight, health, listings, negotiations, orders, product_content, products, purchase_requests, suppliers,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(benchmarks.router)
api_router.include_router(products.router)
api_router.include_router(product_content.router)
api_router.include_router(listings.router)
api_router.include_router(freight.router)
api_router.include_router(purchase_requests.router)
api_router.include_router(negotiations.router)
api_router.include_router(orders.router)
api_router.include_router(approvals.router)
api_router.include_router(dashboard.router)
api_router.include_router(admin_pricing.router)
api_router.include_router(admin_products.router)
api_router.include_router(admin_integrations.router)
api_router.include_router(admin_users.router)
api_router.include_router(suppliers.router)
