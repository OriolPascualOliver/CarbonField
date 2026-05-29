"""
Carbon calculation API endpoint.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from loguru import logger
from sqlmodel import Session

from app.database import get_session
from app.models.result import CarbonCalculation
from app.services.carbon_model import CarbonModel, CarbonInputs, CROP_BIOMASS_REF, SIGPAC_TO_CROP

router = APIRouter(prefix="/carbon", tags=["carbon"])
model = CarbonModel()


def get_db():
    with get_session() as session:
        yield session


class CarbonRequest(BaseModel):
    ref_catastral: Optional[str] = Field(None, description="Referencia catastral de la parcela")
    area_ha: float = Field(..., gt=0, description="Área parcela en hectáreas")
    crop_type: str = Field(..., description=f"Cultivo: {list(CROP_BIOMASS_REF.keys())}")
    tillage_practice: str = Field("conventional", description="conventional|min_tillage|no_till")
    input_level: str = Field("medium", description="low|medium|high|high_manure")
    has_cover_crops: bool = False
    climate_zone: str = "warm_temperate_dry"
    ndvi_mean: Optional[float] = Field(None, ge=0, le=1, description="NDVI medio anual (0-1)")
    sigpac_use: Optional[str] = Field(None, description="Código uso SIGPAC (ej: TA, VI, OL)")


class CarbonResponse(BaseModel):
    area_ha: float
    crop_type: str
    tillage_practice: str
    total_co2e_t_yr: float
    total_carbon_tc_yr: float
    soc_delta_tc_yr: float
    biomass_carbon_tc: float
    confidence: str
    uncertainty_pct: float
    scenarios: dict
    warnings: list[str]
    methodology: str


class ProjectionRequest(BaseModel):
    area_ha: float
    crop_type: str
    tillage_practice: str = "conventional"
    input_level: str = "medium"
    has_cover_crops: bool = False
    ndvi_mean: Optional[float] = None
    improved_tillage: str = "no_till"
    improved_input_level: str = "high"
    improved_cover_crops: bool = True


@router.post("/calculate", response_model=CarbonResponse)
async def calculate_carbon(req: CarbonRequest, db: Session = Depends(get_db)):
    """
    Calcula tCO₂e secuestradas/año para una parcela.
    Si se pasa sigpac_use, auto-detecta crop_type.
    """
    crop = req.crop_type
    if req.sigpac_use and req.sigpac_use in SIGPAC_TO_CROP:
        mapped = SIGPAC_TO_CROP[req.sigpac_use]
        if mapped:
            crop = mapped
            logger.info(f"SIGPAC {req.sigpac_use} → crop: {crop}")

    inputs = CarbonInputs(
        area_ha=req.area_ha,
        crop_type=crop,
        tillage_practice=req.tillage_practice,
        input_level=req.input_level,
        has_cover_crops=req.has_cover_crops,
        climate_zone=req.climate_zone,
        ndvi_mean=req.ndvi_mean,
    )

    result = model.calculate(inputs)

    calculation = CarbonCalculation(
        ref_catastral=req.ref_catastral,
        area_ha=result.area_ha,
        crop_type=result.crop_type,
        tillage_practice=result.tillage_practice,
        input_level=req.input_level,
        has_cover_crops=req.has_cover_crops,
        climate_zone=req.climate_zone,
        ndvi_mean=req.ndvi_mean,
        total_co2e_t_yr=result.total_co2e_t_yr,
        total_carbon_tc_yr=result.total_carbon_tc_yr,
        soc_delta_tc_yr=result.delta_soc_total_tc_yr,
        biomass_carbon_tc=result.biomass_carbon_total_tc,
        confidence=result.confidence,
        uncertainty_pct=result.uncertainty_pct,
        scenarios=result.scenarios,
    )
    db.add(calculation)
    db.commit()
    db.refresh(calculation)

    return CarbonResponse(
        area_ha=result.area_ha,
        crop_type=result.crop_type,
        tillage_practice=result.tillage_practice,
        total_co2e_t_yr=result.total_co2e_t_yr,
        total_carbon_tc_yr=result.total_carbon_tc_yr,
        soc_delta_tc_yr=result.delta_soc_total_tc_yr,
        biomass_carbon_tc=result.biomass_carbon_total_tc,
        confidence=result.confidence,
        uncertainty_pct=result.uncertainty_pct,
        scenarios=result.scenarios,
        warnings=result.warnings,
        methodology=result.methodology,
    )


@router.post("/projection")
async def project_carbon(req: ProjectionRequest):
    """
    Proyección 3 años: práctica actual vs práctica mejorada.
    """
    inputs = CarbonInputs(
        area_ha=req.area_ha,
        crop_type=req.crop_type,
        tillage_practice=req.tillage_practice,
        input_level=req.input_level,
        has_cover_crops=req.has_cover_crops,
        ndvi_mean=req.ndvi_mean,
    )
    changes = {
        "tillage_practice": req.improved_tillage,
        "input_level": req.improved_input_level,
        "has_cover_crops": req.improved_cover_crops,
    }
    df = model.project_3_years(inputs, changes)
    return df.to_dict("records")


@router.get("/crops")
async def list_crops():
    """Lista cultivos soportados con parámetros de referencia."""
    return CROP_BIOMASS_REF


@router.get("/practices")
async def list_practices():
    from app.services.carbon_model import F_MG, F_I
    return {"tillage": F_MG, "input_levels": F_I}
