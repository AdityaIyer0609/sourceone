from fastapi import APIRouter

from app.api.v1 import admin_pricing, benchmarks, health, negotiations, orders, products

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(benchmarks.router)
api_router.include_router(products.router)
api_router.include_router(negotiations.router)
api_router.include_router(orders.router)
api_router.include_router(admin_pricing.router)
