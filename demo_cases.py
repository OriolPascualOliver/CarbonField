"""
Casos de uso reales — parcelas públicas Catalunya
Datos: SIGPAC públicos + NDVI estimado por zona/cultivo

5 casos representativos del sector agrícola catalán:
  1. Cereal secano Lleida (Pla d'Urgell) — cultivo dominante
  2. Viñedo DO Penedès — viticultura
  3. Olivar Garrigues — olivicultura tradicional
  4. Alfalfa regadío Lleida — forrajeras
  5. Almendro secano Terra Alta — frutos secos

Objetivo: demostrar rango de resultados reales para el jurado.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.services.carbon_model import CarbonModel, CarbonInputs
import pandas as pd

model = CarbonModel()

CASOS = [
    {
        "id": "caso_1",
        "nombre": "Cereal secano — Pla d'Urgell (Lleida)",
        "ref_catastral": "25120A00200001",
        "municipio": "Mollerussa",
        "area_ha": 12.5,
        "crop_type": "wheat",
        "tillage_practice": "conventional",
        "input_level": "low",
        "has_cover_crops": False,
        "climate_zone": "warm_temperate_dry",
        "ndvi_mean": 0.42,
        "context": "Explotación familiar típica Lleida. Trigo + cebada rotación. Sin cubiertas.",
    },
    {
        "id": "caso_2",
        "nombre": "Viñedo DO Penedès — Alt Penedès",
        "ref_catastral": "08100A01500023",
        "municipio": "Sant Sadurní d'Anoia",
        "area_ha": 4.2,
        "crop_type": "vineyard",
        "tillage_practice": "min_tillage",
        "input_level": "medium",
        "has_cover_crops": True,
        "climate_zone": "warm_temperate_moist",
        "ndvi_mean": 0.38,
        "context": "Bodega mediana. Cubierta vegetal entre líneas. Labranza mínima.",
    },
    {
        "id": "caso_3",
        "nombre": "Olivar tradicional — Les Garrigues",
        "ref_catastral": "25088A00300012",
        "municipio": "Les Borges Blanques",
        "area_ha": 8.0,
        "crop_type": "olive",
        "tillage_practice": "conventional",
        "input_level": "low",
        "has_cover_crops": False,
        "climate_zone": "warm_temperate_dry",
        "ndvi_mean": 0.33,
        "context": "Olivar centenario secano. DO Les Garrigues. Sin mecanización intensiva.",
    },
    {
        "id": "caso_4",
        "nombre": "Alfalfa regadío — Segrià (Lleida)",
        "ref_catastral": "25178A00100005",
        "municipio": "Alcarràs",
        "area_ha": 6.0,
        "crop_type": "alfalfa",
        "tillage_practice": "min_tillage",
        "input_level": "high",
        "has_cover_crops": False,
        "climate_zone": "warm_temperate_dry",
        "ndvi_mean": 0.65,
        "context": "Regadío canal d'Urgell. Alta biomasa, 4-5 cortes/año.",
    },
    {
        "id": "caso_5",
        "nombre": "Almendro secano — Terra Alta (Tarragona)",
        "ref_catastral": "43154A00200008",
        "municipio": "Gandesa",
        "area_ha": 15.0,
        "crop_type": "almond",
        "tillage_practice": "no_till",
        "input_level": "medium",
        "has_cover_crops": True,
        "climate_zone": "warm_temperate_dry",
        "ndvi_mean": 0.29,
        "context": "Almendro joven (5-8 años). No-till + cubierta espontánea. NDVI bajo por copa pequeña.",
    },
]

def run_all():
    print("=" * 70)
    print("CARBON FARMING TRACKER — Casos de uso reales Catalunya")
    print("Metodología: IPCC 2006 GL Tier 1")
    print("=" * 70)

    rows = []
    for caso in CASOS:
        inputs = CarbonInputs(
            area_ha=caso["area_ha"],
            crop_type=caso["crop_type"],
            tillage_practice=caso["tillage_practice"],
            input_level=caso["input_level"],
            has_cover_crops=caso["has_cover_crops"],
            climate_zone=caso["climate_zone"],
            ndvi_mean=caso["ndvi_mean"],
        )
        result = model.calculate(inputs)

        # Best scenario
        best_name = max(result.scenarios, key=lambda k: result.scenarios[k]["total_co2e_t_yr"])
        best_co2e = result.scenarios[best_name]["total_co2e_t_yr"]
        potential = best_co2e - result.total_co2e_t_yr

        # Market value at 35€/t
        value_eur = result.total_co2e_t_yr * 35

        print(f"\n{'─'*70}")
        print(f"📍 {caso['nombre']}")
        print(f"   {caso['context']}")
        print(f"   Área: {caso['area_ha']} ha · NDVI: {caso['ndvi_mean']} · "
              f"Labranza: {caso['tillage_practice']}")
        print(f"   CO₂e actual:    {result.total_co2e_t_yr:6.2f} tCO₂e/año  "
              f"({result.total_co2e_t_yr/caso['area_ha']:.2f} t/ha/yr)")
        print(f"   Potencial máx:  {best_co2e:6.2f} tCO₂e/año  (+{potential:.2f} si {best_name})")
        print(f"   Valor mercado:  {value_eur:6.0f} €/año  (35€/t, mercado voluntario)")
        print(f"   Confianza: {result.confidence} ±{result.uncertainty_pct:.0f}%")

        rows.append({
            "Caso": caso["nombre"].split("—")[0].strip(),
            "Ha": caso["area_ha"],
            "Cultivo": caso["crop_type"],
            "tCO₂e/yr": result.total_co2e_t_yr,
            "t/ha/yr": round(result.total_co2e_t_yr / caso["area_ha"], 2),
            "Potencial": round(potential, 2),
            "€/yr @35€": round(value_eur, 0),
            "Confianza": result.confidence,
        })

    print(f"\n{'='*70}")
    print("RESUMEN COMPARATIVO")
    print("=" * 70)
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))

    total_co2e = df["tCO₂e/yr"].sum()
    total_area = df["Ha"].sum()
    total_eur = df["€/yr @35€"].sum()
    print(f"\nTotal 5 parcelas: {total_area:.1f} ha · "
          f"{total_co2e:.1f} tCO₂e/yr · {total_eur:.0f} €/yr")
    print(f"Media ponderada:  {total_co2e/total_area:.2f} tCO₂e/ha/yr")

    return df

if __name__ == "__main__":
    df = run_all()
