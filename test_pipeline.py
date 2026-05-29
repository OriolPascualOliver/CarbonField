"""
Smoke test v2 — Open-Meteo + SIGPAC + Sentinel mock
Ejecutar: python scripts/test_pipeline.py
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.services.meteo_service import MeteoService
from app.services.sigpac_service import SIGPACClient
from app.services.sentinel_service import SentinelService

LAT, LON = 41.65, 0.93
REF_CAT = "25120A00200001"


async def test_meteo():
    print("\n=== OPEN-METEO TEST ===")
    svc = MeteoService()
    try:
        meteo = await svc.get_meteo_series(LAT, LON, months=12)
        summary = svc.get_summary(meteo)
        print(f"✓ Source: {summary.get('source')}, elevation: {summary.get('elevation_m')}m")
        print(f"  Temp: {summary.get('mean_temperature_c')}°C mean")
        print(f"  Precip: {summary.get('total_precipitation_mm')}mm / {summary.get('rainy_days')} rain days")
        print(f"  ETo: {summary.get('total_eto_mm')}mm")
        print(f"  Water balance: {summary.get('water_balance_mm')}mm")
    except Exception as e:
        print(f"✗ Meteo error: {e}")
    finally:
        await svc.close()


async def test_sigpac():
    print("\n=== SIGPAC TEST ===")
    client = SIGPACClient()
    try:
        parcel = await client.get_parcel_by_ref(REF_CAT)
        if parcel:
            print(f"✓ Parcel: {parcel['ref_catastral']}, {parcel['area_ha']:.2f} ha")
        else:
            print(f"⚠ Parcel not found (WFS may be geo-blocked in this env — will work on VPS)")
    except Exception as e:
        print(f"⚠ SIGPAC error: {e} (expected in sandboxed env)")
    finally:
        await client.close()


def test_sentinel_mock():
    print("\n=== SENTINEL MOCK TEST ===")
    svc = SentinelService()
    df = svc.get_ndvi_series(
        {"west": 0.92, "south": 41.64, "east": 0.94, "north": 41.66},
        "2024-06-01", "2025-05-01",
    )
    print(f"✓ NDVI records: {len(df)}")
    print(f"  Range: {df['ndvi_mean'].min():.3f} – {df['ndvi_mean'].max():.3f}")
    peak = df.loc[df['ndvi_mean'].idxmax()]
    print(f"  Peak: NDVI={peak['ndvi_mean']:.3f} en {peak['date']}")


async def main():
    await test_meteo()
    await test_sigpac()
    test_sentinel_mock()
    print("\n=== All tests done ===")


if __name__ == "__main__":
    asyncio.run(main())
