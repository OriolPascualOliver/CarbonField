from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class Parcel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ref_catastral: str
    area_ha: float
    uso_sigpac: Optional[str] = None
    municipio: Optional[str] = None
    provincia: Optional[str] = None
    centroid_lat: Optional[float] = None
    centroid_lon: Optional[float] = None
    ndvi_mean: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
