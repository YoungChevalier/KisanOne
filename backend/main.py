"""FastAPI application entry point for KisanOne."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import PyMongoError

from auth import (
    ensure_auth_indexes,
    router as auth_router,
    seed_demo_auth_credentials,
)
from crop_configurations import (
    ensure_crop_configuration_indexes,
    router as crop_configurations_router,
)
from database import close_mongo_connection, get_database
from centres import ensure_centre_indexes, router as centres_router
from employees import ensure_employee_indexes, router as employees_router
from farmers import ensure_farmer_indexes, router as farmers_router
from lots import ensure_lot_indexes, router as lots_router
from procurement_requests import (
    ensure_procurement_request_indexes,
    router as procurement_requests_router,
)
from quality_checks import (
    ensure_quality_check_indexes,
    router as quality_checks_router,
)
from slots import ensure_slot_indexes, router as slots_router
from weighments import (
    ensure_weighment_indexes,
    router as weighments_router,
)
from government_procurements import (
    ensure_government_procurement_indexes,
    router as government_procurements_router,
)
from payments import (
    ensure_payment_indexes,
    router as payments_router,
)
from rulebooks import (
    ensure_quality_evaluation_indexes,
    ensure_rulebook_indexes,
    router as rulebooks_router,
    seed_prototype_rulebooks,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Set up required indexes and release the shared client on shutdown."""
    ensure_farmer_indexes()
    ensure_centre_indexes()
    ensure_crop_configuration_indexes()
    ensure_employee_indexes()
    ensure_slot_indexes()
    ensure_procurement_request_indexes()
    ensure_lot_indexes()
    ensure_quality_check_indexes()
    ensure_weighment_indexes()
    ensure_government_procurement_indexes()
    ensure_payment_indexes()
    ensure_rulebook_indexes()
    ensure_quality_evaluation_indexes()
    ensure_auth_indexes()
    seed_prototype_rulebooks()
    seed_demo_auth_credentials()
    yield
    close_mongo_connection()


app = FastAPI(title="KisanOne API", lifespan=lifespan)

# CORS — allow the frontend dev server and common origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(farmers_router)
app.include_router(centres_router)
app.include_router(crop_configurations_router)
app.include_router(employees_router)
app.include_router(slots_router)
app.include_router(procurement_requests_router)
app.include_router(lots_router)
app.include_router(quality_checks_router)
app.include_router(weighments_router)
app.include_router(government_procurements_router)
app.include_router(payments_router)
app.include_router(rulebooks_router)


@app.get("/health/mongodb", tags=["Health"])
def mongodb_health_check() -> dict[str, str]:
    """Verify that this API can communicate with MongoDB Atlas."""
    try:
        get_database().command("ping")
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB connection is unavailable.",
        ) from error

    return {"status": "ok", "database": get_database().name}
