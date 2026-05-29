"""
Sentinel-2 NDVI pipeline via OpenEO (Copernicus Data Space Ecosystem).

Ventajas de openeo vs sentinelsat:
- API estable y mantenida activamente
- Procesamiento en cloud → no descarga imágenes brutas
- Soporta CDSE directamente

Registro gratuito: https://dataspace.copernicus.eu
Credenciales en .env: COPERNICUS_USER, COPERNICUS_PASSWORD

Nota: sin credenciales activas, usa _get_mock_ndvi() para desarrollo.
"""

import openeo
import numpy as np
import pandas as pd
from datetime import date, timedelta
from loguru import logger
from typing import Optional
from app.core.config import get_settings


CDSE_URL = "https://openeo.dataspace.copernicus.eu"


class SentinelService:
    def __init__(self):
        self.settings = get_settings()
        self._connection: Optional[openeo.Connection] = None

    def _connect(self) -> openeo.Connection:
        if self._connection:
            return self._connection

        if not self.settings.COPERNICUS_USER:
            raise ValueError("COPERNICUS_USER not set in .env")

        logger.info("Connecting to Copernicus Data Space...")
        conn = openeo.connect(CDSE_URL)
        conn.authenticate_oidc_client_credentials(
            client_id=self.settings.COPERNICUS_USER,
            client_secret=self.settings.COPERNICUS_PASSWORD,
        )
        self._connection = conn
        return conn

    def get_ndvi_series(
        self,
        bbox: dict,  # {"west": lon_min, "south": lat_min, "east": lon_max, "north": lat_max}
        start_date: str,  # "YYYY-MM-DD"
        end_date: str,
        max_cloud_cover: int = 20,
    ) -> pd.DataFrame:
        """
        Calcula NDVI mensual medio para un bounding box.
        
        NDVI = (NIR - RED) / (NIR + RED)
        Sentinel-2 bands: B04 (RED, 665nm), B08 (NIR, 842nm)
        
        Returns DataFrame: date, ndvi_mean, ndvi_std, cloud_cover, valid_pixels
        """
        try:
            conn = self._connect()
        except ValueError:
            logger.warning("No Copernicus credentials → using mock NDVI data")
            return self._get_mock_ndvi(start_date, end_date)

        try:
            cube = conn.load_collection(
                "SENTINEL2_L2A",
                spatial_extent=bbox,
                temporal_extent=[start_date, end_date],
                bands=["B04", "B08", "SCL"],  # SCL = Scene Classification Layer
                max_cloud_cover=max_cloud_cover,
            )

            # Máscara nubes usando SCL (valores 4,5 = vegetación/suelo sin nubes)
            scl = cube.band("SCL")
            cloud_mask = (scl == 4) | (scl == 5)

            red = cube.band("B04").apply(lambda x: x * 0.0001)  # DN → reflectancia
            nir = cube.band("B08").apply(lambda x: x * 0.0001)

            ndvi = (nir - red) / (nir + red)
            ndvi_masked = ndvi.mask(~cloud_mask)

            # Reducir a media mensual
            ndvi_monthly = ndvi_masked.aggregate_temporal_period(
                period="month",
                reducer="mean",
            )

            result = ndvi_monthly.download_as_json()
            return self._parse_openeo_result(result)

        except Exception as e:
            logger.error(f"OpenEO error: {e}")
            logger.warning("Falling back to mock NDVI data")
            return self._get_mock_ndvi(start_date, end_date)

    def _parse_openeo_result(self, result: dict) -> pd.DataFrame:
        records = []
        for timestamp, values in result.items():
            flat = np.array(values).flatten()
            valid = flat[~np.isnan(flat)]
            records.append({
                "date": pd.to_datetime(timestamp).date(),
                "ndvi_mean": float(np.mean(valid)) if len(valid) else None,
                "ndvi_std": float(np.std(valid)) if len(valid) else None,
                "valid_pixels": len(valid),
            })
        return pd.DataFrame(records).sort_values("date").reset_index(drop=True)

    def _get_mock_ndvi(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        NDVI sintético para desarrollo/demo.
        Simula patrón estacional mediterráneo (Lleida, cereal).
        
        Patrón real cereal invierno Lleida:
          Oct-Nov: 0.15-0.25 (suelo desnudo/emergencia)
          Dic-Feb: 0.25-0.45 (crecimiento lento)
          Mar-May: 0.55-0.80 (máximo vegetativo)
          Jun:     0.30-0.50 (maduración)
          Jul-Sep: 0.10-0.20 (rastrojo/barbecho)
        """
        logger.info("Using mock NDVI data (development mode)")

        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        months = pd.date_range(start, end, freq="MS")

        seasonal_ndvi = {
            1: 0.35, 2: 0.40, 3: 0.60, 4: 0.75,
            5: 0.70, 6: 0.40, 7: 0.15, 8: 0.12,
            9: 0.14, 10: 0.20, 11: 0.28, 12: 0.30,
        }

        records = []
        for m in months:
            base = seasonal_ndvi[m.month]
            noise = np.random.normal(0, 0.03)
            records.append({
                "date": m.date(),
                "ndvi_mean": round(np.clip(base + noise, 0, 1), 3),
                "ndvi_std": round(abs(np.random.normal(0.04, 0.01)), 3),
                "valid_pixels": np.random.randint(800, 1200),
                "source": "mock",
            })

        return pd.DataFrame(records)

    def bbox_from_geometry(self, geojson_geom: dict, buffer_deg: float = 0.001) -> dict:
        """
        Genera bounding box desde geometría GeoJSON con buffer.
        buffer_deg ≈ 100m en latitudes ibéricas.
        """
        from shapely.geometry import shape
        geom = shape(geojson_geom)
        minx, miny, maxx, maxy = geom.bounds
        return {
            "west": minx - buffer_deg,
            "south": miny - buffer_deg,
            "east": maxx + buffer_deg,
            "north": maxy + buffer_deg,
        }
