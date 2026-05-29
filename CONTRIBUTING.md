# Contributing

## Setup desarrollo

```bash
git clone ...
pip install -r requirements.txt
cp .env.example .env
python scripts/test_carbon.py  # sin red, offline
```

## Tests antes de PR

```bash
python scripts/test_carbon.py    # obligatorio, sin red
python scripts/test_pipeline.py  # requiere red
```

## Áreas donde contribuir

- **Cultivos**: añadir parámetros en `carbon_model.py → CROP_BIOMASS_REF`
- **Zonas climáticas**: ampliar `SOC_REF` con datos regionales
- **NDVI→biomasa**: mejorar correlación con datos de campo
- **Tier 2**: integrar análisis suelo local (SOC medido)
