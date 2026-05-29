"""
Meteo service usando Open-Meteo API.
- 100% gratuito, sin API key
- Cubre España completa
- Incluye ETo FAO directamente (variable et0_fao_evapotranspiration)
- Histórico hasta 1940

Docs: https://open-meteo.com/en/docs

Variables usadas:
  temperature_2m_mean        → temperatura media diaria (°C)
  precipitation_sum          → precipitación acumulada diaria (mm)
  et0_fao_evapotranspiration → ETo FAO-56 calculada internamente (mm)
  shortwave_radiation_sum    → radiación solar (MJ/m²)
  windspeed_10m_max          → vel. viento (km/h)

Nota sobre XEMA: requiere API key de pago (plan estaba incorrecto).
Open-Meteo da los mismos datos con mejor cobertura espacial.
Si se quiere dato de estación exacta, se puede añadir AEMET OpenData (gratuita con registro).
"""

import httpx
import pandas as pd
from datetime import date, timedelta
from loguru import logger
from typing import Optional


OPEN_METEO_BASE = "https://api.open-meteo.com/v1"
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"


class MeteoService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)

    async def get_meteo_series(
        self,
        lat: float,
        lon: float,
        months: int = 12,
    ) -> dict[str, pd.DataFrame]:
        """
        Descarga serie meteo histórica + forecast próximos días.
        
        Returns:
            temperature: DataFrame(date, value) en °C
            precipitation: DataFrame(date, value) en mm
            solar_radiation: DataFrame(date, value) en MJ/m²
            eto: DataFrame(date, eto_mm) ETo FAO-56
            summary: dict con métricas agregadas
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=30 * months)

        # Datos históricos (archive API, más confiable para >7 días)
        archive_data = await self._fetch_archive(lat, lon, start_date, end_date)
        
        if not archive_data:
            logger.warning("Open-Meteo archive failed, using forecast endpoint")
            archive_data = await self._fetch_forecast(lat, lon)

        return self._parse_response(archive_data)

    async def _fetch_archive(
        self, lat: float, lon: float, start: date, end: date
    ) -> Optional[dict]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": [
                "temperature_2m_mean",
                "precipitation_sum",
                "et0_fao_evapotranspiration",
                "shortwave_radiation_sum",
                "windspeed_10m_max",
            ],
            "timezone": "Europe/Madrid",
        }
        try:
            resp = await self.client.get(OPEN_METEO_ARCHIVE, params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Open-Meteo archive error: {e}")
            return None

    async def _fetch_forecast(self, lat: float, lon: float) -> Optional[dict]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": [
                "temperature_2m_mean",
                "precipitation_sum",
                "et0_fao_evapotranspiration",
                "shortwave_radiation_sum",
            ],
            "past_days": 90,
            "forecast_days": 7,
            "timezone": "Europe/Madrid",
        }
        try:
            resp = await self.client.get(f"{OPEN_METEO_BASE}/forecast", params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Open-Meteo forecast error: {e}")
            return None

    def _parse_response(self, data: Optional[dict]) -> dict:
        if not data or "daily" not in data:
            return {
                "temperature": pd.DataFrame(columns=["date", "value"]),
                "precipitation": pd.DataFrame(columns=["date", "value"]),
                "solar_radiation": pd.DataFrame(columns=["date", "value"]),
                "eto": pd.DataFrame(columns=["date", "eto_mm"]),
                "source": "error",
            }

        daily = data["daily"]
        dates = pd.to_datetime(daily["time"]).date

        def make_df(key: str, col: str = "value") -> pd.DataFrame:
            vals = daily.get(key, [])
            df = pd.DataFrame({"date": dates, col: vals})
            return df.dropna(subset=[col]).reset_index(drop=True)

        temp_df = make_df("temperature_2m_mean")
        precip_df = make_df("precipitation_sum")
        solar_df = make_df("shortwave_radiation_sum")
        eto_df = make_df("et0_fao_evapotranspiration", col="eto_mm")

        source_info = {
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "elevation": data.get("elevation"),
            "timezone": data.get("timezone"),
            "source": "open-meteo",
        }

        return {
            "temperature": temp_df,
            "precipitation": precip_df,
            "solar_radiation": solar_df,
            "eto": eto_df,
            **source_info,
        }

    def get_summary(self, meteo: dict) -> dict:
        temp = meteo["temperature"]
        precip = meteo["precipitation"]
        eto = meteo["eto"]

        summary = {
            "source": "open-meteo",
            "elevation_m": meteo.get("elevation"),
        }

        if not temp.empty:
            summary["mean_temperature_c"] = round(temp["value"].mean(), 1)
            summary["max_temperature_c"] = round(temp["value"].max(), 1)
            summary["min_temperature_c"] = round(temp["value"].min(), 1)

        if not precip.empty:
            summary["total_precipitation_mm"] = round(precip["value"].sum(), 1)
            summary["rainy_days"] = int((precip["value"] > 1.0).sum())

        if not eto.empty:
            summary["total_eto_mm"] = round(eto["eto_mm"].sum(), 1)

        if "total_precipitation_mm" in summary and "total_eto_mm" in summary:
            summary["water_balance_mm"] = round(
                summary["total_precipitation_mm"] - summary["total_eto_mm"], 1
            )

        return summary

    async def close(self):
        await self.client.aclose()


_meteo_service: Optional[MeteoService] = None


def get_meteo_service() -> MeteoService:
    global _meteo_service
    if _meteo_service is None:
        _meteo_service = MeteoService()
    return _meteo_service
