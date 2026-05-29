"""
Main data pipeline endpoint.
Input:  referencia catastral
Output: NDVI histórico + meteo últimos 12 meses
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import date, timedelta
from loguru import logger

from app.services.sigpac_service import SIGPACClient
from app.services.xema_service import get_xema_client
from app.services.sentinel_service import SentinelService


router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class PipelineRequest(BaseModel):
    ref_catastral: str
    months_history: int = 12


class PipelineResponse(BaseModel):
    ref_catastral: str
    parcel: dict
    ndvi_series: list[dict]
    meteo_summary: dict
    status: str


@router.post("/run", response_model=PipelineResponse)
async def run_pipeline(req: PipelineRequest):
    """
    Pipeline completo para una parcela:
    1. SIGPAC  → geometría y metadatos
    2. Sentinel-2 → NDVI histórico mensual
    3. XEMA   → temperatura, precipitación, ETo
    """
    logger.info(f"Pipeline start: {req.ref_catastral}")

    # 1. SIGPAC
    sigpac = SIGPACClient()
    parcel = await sigpac.get_parcel_by_ref(req.ref_catastral)
    if not parcel:
        raise HTTPException(
            status_code=404,
            detail=f"Parcel {req.ref_catastral} not found in SIGPAC"
        )
    await sigpac.close()

    lat = parcel["centroid"]["lat"]
    lon = parcel["centroid"]["lon"]

    # 2. Sentinel-2 NDVI (mock si no hay credenciales)
    sentinel = SentinelService()
    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=30 * req.months_history)).isoformat()
    bbox = sentinel.bbox_from_geometry(parcel["geometry"])
    ndvi_df = sentinel.get_ndvi_series(bbox, start_date, end_date)
    ndvi_records = ndvi_df.to_dict("records")
    for r in ndvi_records:
        if hasattr(r.get("date"), "isoformat"):
            r["date"] = r["date"].isoformat()

    # 3. XEMA meteo
    xema = get_xema_client()
    try:
        meteo = await xema.get_meteo_series(lat, lon, months=req.months_history)
        station = meteo.get("station", {})
        precip_df = meteo["precipitation"]
        temp_df = meteo["temperature"]
        eto_df = meteo["eto"]

        meteo_summary = {
            "station_name": station.get("nom", "unknown"),
            "station_code": station.get("codi", "unknown"),
            "total_precipitation_mm": round(precip_df["value"].sum(), 1) if not precip_df.empty else None,
            "mean_temperature_c": round(temp_df["value"].mean(), 1) if not temp_df.empty else None,
            "total_eto_mm": round(eto_df["eto_mm"].sum(), 1) if not eto_df.empty else None,
            "water_balance_mm": None,
        }
        if meteo_summary["total_precipitation_mm"] and meteo_summary["total_eto_mm"]:
            meteo_summary["water_balance_mm"] = round(
                meteo_summary["total_precipitation_mm"] - meteo_summary["total_eto_mm"], 1
            )
    except Exception as e:
        logger.error(f"XEMA error: {e}")
        meteo_summary = {"error": str(e)}

    logger.info(f"Pipeline complete: {req.ref_catastral}")
    return PipelineResponse(
        ref_catastral=req.ref_catastral,
        parcel=parcel,
        ndvi_series=ndvi_records,
        meteo_summary=meteo_summary,
        status="ok",
    )


@router.get("/health")
async def health():
    return {"status": "ok", "services": ["sigpac", "xema", "sentinel2"]}
