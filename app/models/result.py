from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, Column
from sqlalchemy import JSON


class CarbonCalculation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ref_catastral: Optional[str] = None
    area_ha: float
    crop_type: str
    tillage_practice: str
    input_level: str
    has_cover_crops: bool = False
    climate_zone: str = "warm_temperate_dry"
    ndvi_mean: Optional[float] = None
    total_co2e_t_yr: float
    total_carbon_tc_yr: float
    soc_delta_tc_yr: float
    biomass_carbon_tc: float
    confidence: str
    uncertainty_pct: float
    scenarios: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
