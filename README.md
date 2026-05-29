# 🌱 Carbon Farming Tracker

Estimación de secuestro CO₂ agrícola via satélite y datos catastrales públicos.

**Demo:** [https://carbon.tudominio.com](https://carbon.tudominio.com)

---

## ¿Qué hace?

Dado una referencia catastral española (SIGPAC), calcula automáticamente:

- **tCO₂e/año** secuestradas por la parcela (metodología IPCC Tier 1)
- NDVI histórico mensual desde Sentinel-2 (ESA Copernicus)
- Comparativa de 4 escenarios de prácticas agrícolas
- Proyección 3 años con/sin cambio de práctica
- Valor estimado en mercados de carbono voluntarios (€/año)
- Export PDF informe para presentación a compradores de créditos

---

## Fuentes de datos (todas públicas y gratuitas)

| Fuente | Datos | API |
|--------|-------|-----|
| [Sentinel-2 / Copernicus CDSE](https://dataspace.copernicus.eu) | NDVI mensual 10m | OpenEO (registro gratuito) |
| [SIGPAC / FEGA](https://sigpac.mapama.gob.es) | Geometría parcelaria, uso suelo | WFS público |
| [Open-Meteo](https://open-meteo.com) | Temperatura, precipitación, ETo FAO | REST, sin API key |

---

## Stack

```
Backend:   FastAPI + SQLModel + PostgreSQL
Motor CO₂: Python + NumPy/Pandas (IPCC Tier 1)
Geo:       GeoPandas + Rasterio + OpenEO
Frontend:  Streamlit + Folium
Infra:     Docker + Hetzner CX22 (~5€/mes)
```

---

## Instalación local

### Prerequisitos

- Python 3.12+
- PostgreSQL 16+ (o usar Docker)
- Cuenta Copernicus Data Space: [registro gratuito](https://dataspace.copernicus.eu/account/keycloak/realms/CDSE/login-actions/registration)

### Setup

```bash
git clone https://github.com/tuusuario/carbon-tracker.git
cd carbon-tracker

# Dependencias del sistema (Ubuntu/Debian)
sudo apt-get install -y libgdal-dev gdal-bin libgeos-dev libproj-dev

# Python deps
pip install -r requirements.txt

# Configuración
cp .env.example .env
# Editar .env con tus credenciales Copernicus
```

### Variables de entorno

```bash
# .env
DATABASE_URL=postgresql://user:password@localhost:5432/carbon_tracker
COPERNICUS_USER=tu_email@ejemplo.com
COPERNICUS_PASSWORD=tu_password
```

> **Sin credenciales Copernicus:** la app funciona con NDVI sintético (mock estacional).
> Los demás módulos (CO₂, meteo, SIGPAC) no requieren auth.

### Arrancar

```bash
# Solo Streamlit app (recomendado para demo)
./run_app.sh
# → http://localhost:8501

# Con Docker (incluye PostgreSQL)
docker compose up
# Streamlit → :8501  |  FastAPI → :8000  |  API docs → :8000/docs
```

### Tests

```bash
# Pipeline completo (requiere red para Open-Meteo + SIGPAC)
python scripts/test_pipeline.py

# Motor CO₂ (sin red, funciona offline)
python scripts/test_carbon.py

# Casos de uso reales Catalunya
python scripts/demo_cases.py
```

---

## Metodología

### Motor CO₂ — IPCC Tier 1

Basado en **IPCC 2006 Guidelines for National GHG Inventories, Vol. 4 (AFOLU), Cap. 2 y 5**.

```
ΔC_total = ΔC_SOC + ΔC_biomass

ΔC_SOC     = A × SOC_ref × F_lu × F_mg × F_i   (transición lineal 20 años)
ΔC_biomass = A × AG_biomass × (1+R) × CF × (1-HI) × kh

Donde:
  SOC_ref  = carbono referencia suelo por zona climática (tC/ha)
  F_lu     = factor uso suelo (IPCC Table 5.5)
  F_mg     = factor gestión labranza (1.0–1.10)
  F_i      = factor inputs orgánicos (0.92–1.17)
  R        = ratio raíz:tallo por cultivo
  CF       = 0.47 (fracción carbono biomasa, IPCC default)
  HI       = harvest index por cultivo
  kh       = 0.15 (factor humificación, Panettieri et al. 2017)

Conversión: 1 tC = 3.667 tCO₂e
```

**Cultivos soportados:** trigo, cebada, maíz, girasol, alfalfa, viñedo, olivo, almendro, cubierta vegetal, barbecho.

**Zonas climáticas:** mediterráneo seco/húmedo, meseta norte, cornisa cantábrica.

### NDVI → Biomasa

Relación empírica lineal calibrada con datos MODIS-España (Baret & Guyot 1991, adaptado):

```
Biomass_ha = 3.0 + (NDVI - 0.2) × 25
```

Con blend 60% NDVI-derivado / 40% referencia por cultivo para robustez ante anomalías.

### Limitaciones explícitas

- **Tier 1**: incertidumbre ±30-40% sin datos de suelo locales
- No incluye emisiones N₂O ni CH₄ del suelo
- Correlación NDVI-biomasa lineal; puede desviarse en cultivos leñosos jóvenes
- Sin verificación de campo ni auditoría tercera parte

---

## Estructura del proyecto

```
carbon-tracker/
├── app/
│   ├── api/
│   │   ├── carbon.py        # Endpoints CO₂ (calculate, projection, crops)
│   │   └── pipeline.py      # Endpoint pipeline completo (SIGPAC+NDVI+meteo)
│   ├── core/
│   │   └── config.py        # Settings (pydantic-settings)
│   ├── models/
│   │   └── parcel.py        # SQLModel DB models
│   └── services/
│       ├── carbon_model.py  # Motor IPCC Tier 1 ← núcleo del proyecto
│       ├── meteo_service.py # Open-Meteo client
│       ├── sentinel_service.py # OpenEO + mock NDVI
│       └── sigpac_service.py   # SIGPAC WFS client
├── streamlit_app/
│   ├── app.py               # UI principal (mapa, dashboard, PDF)
│   └── pdf_export.py        # Generador informes ReportLab
├── scripts/
│   ├── test_pipeline.py     # Smoke test pipeline completo
│   ├── test_carbon.py       # Tests motor CO₂
│   └── demo_cases.py        # 5 casos reales Catalunya
├── deploy/
│   ├── nginx.conf           # Reverse proxy config
│   └── setup_vps.sh         # Deploy script Hetzner Ubuntu 24.04
├── .env.example
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## API Reference

Con `docker compose up` o `uvicorn app.main:app`, docs interactivos en `http://localhost:8000/docs`.

### `POST /carbon/calculate`

```json
{
  "area_ha": 10.0,
  "crop_type": "wheat",
  "tillage_practice": "no_till",
  "input_level": "high",
  "has_cover_crops": true,
  "ndvi_mean": 0.45,
  "climate_zone": "warm_temperate_dry"
}
```

Respuesta:
```json
{
  "total_co2e_t_yr": 31.48,
  "confidence": "medium",
  "uncertainty_pct": 30.0,
  "scenarios": { "baseline_conventional": {...}, "no_till_cover_crops": {...} },
  "methodology": "IPCC_Tier1"
}
```

### `POST /carbon/projection`

Proyección 3 años comparando práctica actual vs mejorada.

### `POST /pipeline/run`

Pipeline completo: ref. catastral → NDVI + meteo + CO₂.

```json
{ "ref_catastral": "25120A00200001", "months_history": 12 }
```

---

## Deploy en producción

```bash
# Hetzner CX22 (~5€/mes), Ubuntu 24.04
# Requiere dominio con DNS apuntando al VPS

bash deploy/setup_vps.sh tudominio.com
# Instala: Python, Nginx, Certbot (SSL), Supervisor, PostgreSQL
# App disponible en https://tudominio.com en ~5 minutos
```

---

## Referencias

- IPCC (2006). *2006 IPCC Guidelines for National GHG Inventories*, Vol. 4 AFOLU. IGES, Japan.
- Panettieri M. et al. (2017). Carbon sequestration under different management practices in Mediterranean soils. *Soil & Tillage Research*, 174, 119–128.
- Poeplau C. & Don A. (2015). Carbon sequestration in agricultural soils via cultivation of cover crops. *Agriculture, Ecosystems & Environment*, 200, 33–41.
- Baret F. & Guyot G. (1991). Potentials and limits of vegetation indices. *Remote Sensing of Environment*, 35, 161–173.

---

## Licencia

MIT — ver [LICENSE](LICENSE)

---

*Desarrollado para la convocatoria Agri-Tech 2026 · Junio 2026*
