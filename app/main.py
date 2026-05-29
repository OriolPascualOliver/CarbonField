from fastapi import FastAPI

from app.api.carbon import router as carbon_router
from app.api.pipeline import router as pipeline_router
from app.database import init_db
from app.models.parcel import Parcel
from app.models.result import CarbonCalculation

app = FastAPI(
    title="Carbon Farming Tracker API",
    description="API endpoints for carbon estimation and parcel pipeline",
    version="0.1.0",
)

app.include_router(carbon_router)
app.include_router(pipeline_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "Carbon Farming Tracker"}
