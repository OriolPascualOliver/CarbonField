"""
Motor de cálculo CO₂ — IPCC Tier 1 simplificado.

Metodología base:
  IPCC 2006 GL, Vol 4 (Agriculture, Forestry and Other Land Use)
  Cap 2 (Generic Methodologies), Cap 5 (Cropland)

Componentes del secuestro:
  1. SOC (Soil Organic Carbon) — cambio carbono orgánico suelo
  2. Above-ground biomass — biomasa aérea (cultivo + residuos)
  3. Below-ground biomass — raíces (ratio R:S por cultivo)

Fórmula principal (Ec. 2.25 IPCC):
  ΔC_total = ΔC_SOC + ΔC_biomass

  ΔC_SOC = A * SOC_ref * F_lu * F_mg * F_i - SOC_0
    A      = área (ha)
    SOC_ref = carbono referencia suelo (t C/ha) — por zona climática
    F_lu   = factor uso suelo
    F_mg   = factor gestión (labranza)
    F_i    = factor inputs (residuos, cubiertas)

  ΔC_biomass = A * (AG_biomass * (1 + R_ratio) * CF)
    AG_biomass = biomasa aérea estimada (t MS/ha) desde NDVI
    R_ratio    = ratio raíz:tallo
    CF         = fracción carbono (0.47 IPCC default)

Conversión a CO₂e:
  tCO₂e = tC * 44/12 = tC * 3.667

LIMITACIONES explícitas (mencionar en UI):
  - Tier 1: sin datos de suelo locales → incertidumbre ±30-50%
  - Biomasa desde NDVI: correlación empírica, no medición directa
  - No incluye N₂O (óxido nitroso) ni CH₄ — emisiones GEI suelo
  - Validez: zona climática mediterránea, cultivos anuales/permanentes España
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger


# ---------------------------------------------------------------------------
# IPCC Tier 1 Reference Data
# ---------------------------------------------------------------------------

# SOC de referencia por zona climática (tC/ha, 0-30cm)
# Fuente: IPCC 2006 GL Table 2.3
# Zona mediterránea España: Warm Temperate Dry
SOC_REF = {
    "warm_temperate_dry": 38.0,    # Catalunya interior, Lleida, Zaragoza
    "warm_temperate_moist": 47.0,  # Costa mediterránea húmeda
    "cool_temperate_dry": 50.0,    # Meseta norte
    "cool_temperate_moist": 65.0,  # Galicia, Cornisa Cantábrica
}

# Factores uso suelo F_lu (IPCC Table 5.5)
# Referencia: cropland en uso histórico > 20 años = 1.0
F_LU = {
    "arable_land": 1.0,
    "vineyard": 1.0,
    "olive_grove": 1.0,
    "citrus": 1.0,
    "dry_fruit_trees": 1.0,
    "irrigated_fruit_trees": 1.0,
    "pasture": 1.14,       # mayor acumulación SOC que arable
    "shrub_pasture": 1.14,
    "fallow": 0.82,
    "forest": 1.0,         # referencia, no calculamos forestry aquí
}

# Factores gestión F_mg — impacto labranza en SOC (IPCC Table 5.5)
F_MG = {
    "conventional":  1.0,   # labranza convencional (referencia)
    "min_tillage":   1.02,  # labranza reducida (+2% SOC)
    "no_till":       1.10,  # sin labranza (+10% SOC)
    "ridge_till":    1.02,
}

# Factores inputs F_i — residuos y materia orgánica (IPCC Table 5.5)
F_I = {
    "low":          0.92,  # sin residuos, sin cubiertas
    "medium":       1.0,   # gestión residuos estándar (referencia)
    "high":         1.11,  # cubiertas vegetales, compost
    "high_manure":  1.17,  # cubiertas + estiércol
}

# Biomasa aérea de referencia por cultivo (t MS/ha)
# Fuente: FAO crop stats + literatura española
# Usado como referencia para calibrar NDVI→biomasa
CROP_BIOMASS_REF = {
    "wheat":          {"ag_biomass": 8.5,  "r_ratio": 0.22, "harvest_index": 0.40},
    "barley":         {"ag_biomass": 7.5,  "r_ratio": 0.22, "harvest_index": 0.45},
    "corn":           {"ag_biomass": 18.0, "r_ratio": 0.22, "harvest_index": 0.45},
    "sunflower":      {"ag_biomass": 9.0,  "r_ratio": 0.15, "harvest_index": 0.30},
    "alfalfa":        {"ag_biomass": 15.0, "r_ratio": 0.40, "harvest_index": 0.65},
    "vineyard":       {"ag_biomass": 4.5,  "r_ratio": 0.32, "harvest_index": 0.35},
    "olive":          {"ag_biomass": 6.0,  "r_ratio": 0.35, "harvest_index": 0.25},
    "almond":         {"ag_biomass": 5.0,  "r_ratio": 0.35, "harvest_index": 0.30},
    "cover_crop":     {"ag_biomass": 3.0,  "r_ratio": 0.25, "harvest_index": 0.0},
    "fallow":         {"ag_biomass": 1.5,  "r_ratio": 0.20, "harvest_index": 0.0},
    "generic_annual": {"ag_biomass": 7.0,  "r_ratio": 0.22, "harvest_index": 0.40},
}

# SIGPAC use → crop type mapping
SIGPAC_TO_CROP = {
    "TA": "generic_annual",  # tierra arable
    "VI": "vineyard",
    "OL": "olive",
    "CF": "generic_annual",  # cítricos
    "FS": "almond",          # frutales secos
    "FY": "generic_annual",  # frutales regadío
    "PA": "alfalfa",         # pasto
    "PS": "alfalfa",
    "MT": None,              # monte — no calculamos
}

# Fracción carbono en biomasa seca (IPCC default)
CF_BIOMASS = 0.47

# Ratio tC → tCO₂e
C_TO_CO2 = 44 / 12  # = 3.667


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class CarbonInputs:
    """Inputs para el cálculo de secuestro."""
    area_ha: float
    crop_type: str                  # key de CROP_BIOMASS_REF
    tillage_practice: str           # key de F_MG
    input_level: str                # key de F_I ("low"/"medium"/"high")
    has_cover_crops: bool = False
    climate_zone: str = "warm_temperate_dry"
    ndvi_mean: Optional[float] = None   # media anual NDVI
    ndvi_series: Optional[list] = None  # serie mensual para ajuste estacional
    years: int = 1                  # horizonte temporal


@dataclass
class CarbonResult:
    """Resultado del cálculo CO₂."""
    # Inputs echo
    area_ha: float
    crop_type: str
    tillage_practice: str

    # SOC component
    soc_ref_t_ha: float          # SOC referencia zona
    soc_current_t_ha: float      # SOC estimado con prácticas actuales
    delta_soc_t_ha_yr: float     # cambio SOC anual (tC/ha/año)
    delta_soc_total_tc_yr: float # cambio SOC total parcela (tC/año)

    # Biomass component
    ag_biomass_t_ha: float       # biomasa aérea (tMS/ha)
    bg_biomass_t_ha: float       # biomasa subterránea (tMS/ha)
    biomass_carbon_tc_ha: float  # carbono en biomasa (tC/ha)
    biomass_carbon_total_tc: float

    # Totals
    total_carbon_tc_yr: float    # tC secuestradas/año
    total_co2e_t_yr: float       # tCO₂e secuestradas/año

    # Scenarios comparison
    scenarios: dict = field(default_factory=dict)

    # Metadata
    methodology: str = "IPCC_Tier1"
    confidence: str = "low"
    uncertainty_pct: float = 40.0
    warnings: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Main model
# ---------------------------------------------------------------------------

class CarbonModel:
    """
    Motor IPCC Tier 1 para estimación de secuestro de carbono.
    
    Uso:
        model = CarbonModel()
        result = model.calculate(inputs)
    """

    def calculate(self, inputs: CarbonInputs) -> CarbonResult:
        warnings = []

        # Validar inputs
        if inputs.crop_type not in CROP_BIOMASS_REF:
            logger.warning(f"Unknown crop '{inputs.crop_type}', using generic_annual")
            inputs.crop_type = "generic_annual"
            warnings.append("Cultivo desconocido → usando parámetros genéricos anuales")

        crop_params = CROP_BIOMASS_REF[inputs.crop_type]
        soc_ref = SOC_REF.get(inputs.climate_zone, SOC_REF["warm_temperate_dry"])

        # --- SOC calculation (IPCC Eq. 2.25) ---
        f_lu = F_LU.get(inputs.crop_type, 1.0)
        f_mg = F_MG.get(inputs.tillage_practice, 1.0)

        # Ajuste F_i por cubiertas
        if inputs.has_cover_crops and inputs.input_level == "medium":
            f_i = F_I["high"]
            warnings.append("Cubiertas vegetales detectadas → F_i ajustado a 'high'")
        else:
            f_i = F_I.get(inputs.input_level, 1.0)

        soc_current = soc_ref * f_lu * f_mg * f_i

        # Delta SOC anual = diferencia respecto referencia (20 años equilibrio IPCC)
        # Tier 1: se asume transición lineal en 20 años
        delta_soc_ha_yr = (soc_current - soc_ref) / 20.0

        delta_soc_total = delta_soc_ha_yr * inputs.area_ha

        # --- Biomass calculation ---
        ag_biomass = self._estimate_ag_biomass(
            crop_params["ag_biomass"],
            inputs.ndvi_mean,
        )
        bg_biomass = ag_biomass * crop_params["r_ratio"]
        total_biomass = ag_biomass + bg_biomass
        biomass_c_ha = total_biomass * CF_BIOMASS

        # Sólo fracción que permanece en suelo (residuos post-cosecha)
        # harvest_index = fracción que se retira → (1 - HI) queda en campo
        residue_fraction = 1.0 - crop_params["harvest_index"]

        # Factor humificación kh: fracción de residuos que se incorpora
        # a SOC estable (fracción húmica). El resto mineraliza → CO₂.
        # kh = 0.15 (15%) — valor medio literatura mediterránea
        # Refs: Panettieri et al. 2017 (Spain), Poeplau & Don 2015 (meta-análisis)
        # Sin kh el modelo sobreestima ×6-7 vs valores reales. Bug corregido.
        KH_HUMIFICATION = 0.15
        biomass_c_retained_ha = biomass_c_ha * residue_fraction * KH_HUMIFICATION
        biomass_c_retained_total = biomass_c_retained_ha * inputs.area_ha

        # --- Totals ---
        total_c_yr = delta_soc_total + biomass_c_retained_total
        total_co2e_yr = total_c_yr * C_TO_CO2

        # Confidence assessment
        confidence, uncertainty = self._assess_confidence(inputs)
        if confidence == "low":
            warnings.append("Tier 1 sin datos suelo locales → incertidumbre ±40%")

        # --- Scenarios ---
        scenarios = self._calculate_scenarios(inputs, soc_ref, crop_params)

        return CarbonResult(
            area_ha=inputs.area_ha,
            crop_type=inputs.crop_type,
            tillage_practice=inputs.tillage_practice,
            soc_ref_t_ha=round(soc_ref, 2),
            soc_current_t_ha=round(soc_current, 2),
            delta_soc_t_ha_yr=round(delta_soc_ha_yr, 4),
            delta_soc_total_tc_yr=round(delta_soc_total, 3),
            ag_biomass_t_ha=round(ag_biomass, 2),
            bg_biomass_t_ha=round(bg_biomass, 2),
            biomass_carbon_tc_ha=round(biomass_c_retained_ha, 3),
            biomass_carbon_total_tc=round(biomass_c_retained_total, 3),
            total_carbon_tc_yr=round(total_c_yr, 3),
            total_co2e_t_yr=round(total_co2e_yr, 3),
            scenarios=scenarios,
            confidence=confidence,
            uncertainty_pct=uncertainty,
            warnings=warnings,
        )

    def _estimate_ag_biomass(
        self,
        ref_biomass: float,
        ndvi_mean: Optional[float],
    ) -> float:
        """
        Estima biomasa aérea.

        Con NDVI: relación empírica lineal calibrada con datos MODIS-España.
          Biomass = a * NDVI + b
          Calibración: NDVI 0.2 → ~3 tMS/ha, NDVI 0.8 → ~18 tMS/ha
          (válida para cultivos anuales mediterráneos)

        Sin NDVI: usa valor de referencia por cultivo.
        """
        if ndvi_mean is None or ndvi_mean <= 0:
            return ref_biomass

        # Relación empírica lineal (Baret & Guyot 1991, adaptado zona mediterránea)
        ndvi_biomass = max(0, 3.0 + (ndvi_mean - 0.2) * (18.0 - 3.0) / (0.8 - 0.2))

        # Blend: 60% NDVI-derived, 40% crop reference (robustez ante NDVI anómalo)
        blended = 0.6 * ndvi_biomass + 0.4 * ref_biomass
        return round(blended, 2)

    def _assess_confidence(self, inputs: CarbonInputs) -> tuple[str, float]:
        """
        Evalúa nivel de confianza del cálculo.
        
        High: NDVI real + datos suelo locales (no Tier 1)
        Medium: NDVI real disponible
        Low: sin NDVI, sólo referencias tabuladas
        """
        if inputs.ndvi_mean is not None and inputs.ndvi_mean > 0:
            return "medium", 30.0
        return "low", 40.0

    def _calculate_scenarios(
        self, inputs: CarbonInputs, soc_ref: float, crop_params: dict
    ) -> dict:
        """
        Calcula 4 escenarios de prácticas para comparativa en dashboard.
        """
        scenarios = {}
        practice_combos = {
            "baseline_conventional": ("conventional", "low", False),
            "min_tillage":           ("min_tillage",  "medium", False),
            "cover_crops":           ("min_tillage",  "high",   True),
            "no_till_cover_crops":   ("no_till",      "high",   True),
        }

        for name, (tillage, input_lvl, cover) in practice_combos.items():
            f_mg = F_MG[tillage]
            f_i = F_I["high"] if cover else F_I[input_lvl]
            f_lu = F_LU.get(inputs.crop_type, 1.0)

            soc = soc_ref * f_lu * f_mg * f_i
            delta_soc = (soc - soc_ref) / 20.0 * inputs.area_ha

            ag_b = self._estimate_ag_biomass(crop_params["ag_biomass"], inputs.ndvi_mean)
            residue = 1.0 - crop_params["harvest_index"]
            biomass_c = ag_b * (1 + crop_params["r_ratio"]) * CF_BIOMASS * residue * 0.15 * inputs.area_ha

            total_c = delta_soc + biomass_c
            total_co2e = total_c * C_TO_CO2

            scenarios[name] = {
                "tillage": tillage,
                "input_level": input_lvl,
                "cover_crops": cover,
                "delta_soc_tc_yr": round(delta_soc, 3),
                "biomass_carbon_tc": round(biomass_c, 3),
                "total_co2e_t_yr": round(total_co2e, 3),
            }

        return scenarios

    def project_3_years(
        self, inputs: CarbonInputs, practice_changes: Optional[dict] = None
    ) -> pd.DataFrame:
        """
        Proyección 3 años con práctica actual y alternativa.
        Útil para dashboard "¿qué pasa si cambio a no-till?"
        
        practice_changes: dict con overrides para año 2 y 3
          ej: {"tillage_practice": "no_till", "has_cover_crops": True}
        """
        rows = []
        for year in range(1, 4):
            current_inputs = CarbonInputs(
                area_ha=inputs.area_ha,
                crop_type=inputs.crop_type,
                tillage_practice=inputs.tillage_practice,
                input_level=inputs.input_level,
                has_cover_crops=inputs.has_cover_crops,
                climate_zone=inputs.climate_zone,
                ndvi_mean=inputs.ndvi_mean,
                years=year,
            )
            result = self.calculate(current_inputs)

            row = {
                "year": year,
                "scenario": "current",
                "co2e_t": result.total_co2e_t_yr,
                "soc_delta_tc": result.delta_soc_total_tc_yr,
                "biomass_tc": result.biomass_carbon_total_tc,
            }
            rows.append(row)

            if practice_changes and year >= 2:
                alt_inputs = CarbonInputs(
                    area_ha=inputs.area_ha,
                    crop_type=inputs.crop_type,
                    tillage_practice=practice_changes.get("tillage_practice", inputs.tillage_practice),
                    input_level=practice_changes.get("input_level", inputs.input_level),
                    has_cover_crops=practice_changes.get("has_cover_crops", inputs.has_cover_crops),
                    climate_zone=inputs.climate_zone,
                    ndvi_mean=inputs.ndvi_mean,
                    years=year,
                )
                alt_result = self.calculate(alt_inputs)
                rows.append({
                    "year": year,
                    "scenario": "improved",
                    "co2e_t": alt_result.total_co2e_t_yr,
                    "soc_delta_tc": alt_result.delta_soc_total_tc_yr,
                    "biomass_tc": alt_result.biomass_carbon_total_tc,
                })

        return pd.DataFrame(rows)
