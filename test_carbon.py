"""
Test motor CO₂ — no requiere APIs externas.
Ejecutar: python scripts/test_carbon.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.services.carbon_model import CarbonModel, CarbonInputs
import json

model = CarbonModel()

# ---- Test 1: cereal convencional, sin NDVI ----
print("\n=== TEST 1: Trigo convencional, 10 ha, sin NDVI ===")
inputs = CarbonInputs(
    area_ha=10.0,
    crop_type="wheat",
    tillage_practice="conventional",
    input_level="medium",
    has_cover_crops=False,
    climate_zone="warm_temperate_dry",
    ndvi_mean=None,
)
r = model.calculate(inputs)
print(f"SOC ref:       {r.soc_ref_t_ha} tC/ha")
print(f"SOC actual:    {r.soc_current_t_ha} tC/ha")
print(f"ΔSOC/año:      {r.delta_soc_t_ha_yr} tC/ha/año")
print(f"Biomasa aérea: {r.ag_biomass_t_ha} tMS/ha")
print(f"Carbono biom.: {r.biomass_carbon_tc_ha} tC/ha")
print(f"TOTAL CO₂e:    {r.total_co2e_t_yr} tCO₂e/año  ← resultado clave")
print(f"Confianza:     {r.confidence} (±{r.uncertainty_pct}%)")
print(f"Warnings:      {r.warnings}")

# ---- Test 2: mismo campo, no-till + cubiertas ----
print("\n=== TEST 2: Mismo campo, no-till + cubiertas vegetales ===")
inputs2 = CarbonInputs(
    area_ha=10.0,
    crop_type="wheat",
    tillage_practice="no_till",
    input_level="high",
    has_cover_crops=True,
    climate_zone="warm_temperate_dry",
    ndvi_mean=None,
)
r2 = model.calculate(inputs2)
print(f"ΔSOC/año:   {r2.delta_soc_t_ha_yr} tC/ha/año  (vs {r.delta_soc_t_ha_yr})")
print(f"TOTAL CO₂e: {r2.total_co2e_t_yr} tCO₂e/año  (vs {r.total_co2e_t_yr})")
delta = r2.total_co2e_t_yr - r.total_co2e_t_yr
print(f"Mejora:     +{delta:.2f} tCO₂e/año por cambio de práctica")

# ---- Test 3: con NDVI real ----
print("\n=== TEST 3: Olivar 5 ha, NDVI=0.45 (real desde Sentinel) ===")
inputs3 = CarbonInputs(
    area_ha=5.0,
    crop_type="olive",
    tillage_practice="min_tillage",
    input_level="medium",
    has_cover_crops=False,
    ndvi_mean=0.45,
)
r3 = model.calculate(inputs3)
print(f"Biomasa (NDVI-calibrada): {r3.ag_biomass_t_ha} tMS/ha")
print(f"TOTAL CO₂e: {r3.total_co2e_t_yr} tCO₂e/año")
print(f"Confianza:  {r3.confidence} (±{r3.uncertainty_pct}%)")

# ---- Test 4: escenarios comparativos ----
print("\n=== TEST 4: Comparativa escenarios (misma parcela trigo 10ha) ===")
print(f"{'Escenario':<30} {'tCO₂e/año':>10}")
print("-" * 42)
for name, s in r.scenarios.items():
    print(f"{name:<30} {s['total_co2e_t_yr']:>10.2f}")

# ---- Test 5: proyección 3 años ----
print("\n=== TEST 5: Proyección 3 años — convencional vs no-till+cubiertas ===")
df = model.project_3_years(
    inputs,
    practice_changes={"tillage_practice": "no_till", "input_level": "high", "has_cover_crops": True}
)
print(df.to_string(index=False))

print("\n=== Motor CO₂ OK ===")
