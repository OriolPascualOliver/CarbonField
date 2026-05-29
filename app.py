"""
Carbon Farming Tracker — Streamlit App
Semana 3: UI completa

Flujo:
  1. Input ref. catastral (o coordenadas manual para demo)
  2. Mapa parcela (Folium)
  3. Configurar cultivo + prácticas
  4. Dashboard CO₂: resultado, escenarios, proyección 3 años
  5. Export PDF informe
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.services.carbon_model import (
    CarbonModel, CarbonInputs,
    CROP_BIOMASS_REF, F_MG, F_I, SIGPAC_TO_CROP
)
from app.services.sentinel_service import SentinelService
from streamlit_app.pdf_export import generate_pdf_report

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Carbon Farming Tracker",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS
st.markdown("""
<style>
    .metric-card {
        background: #f0f7f0;
        border-left: 4px solid #2d6a4f;
        padding: 1rem;
        border-radius: 4px;
        margin: 0.5rem 0;
    }
    .co2-big {
        font-size: 2.5rem;
        font-weight: 700;
        color: #2d6a4f;
    }
    .warning-box {
        background: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 0.75rem;
        border-radius: 4px;
        font-size: 0.85rem;
    }
    .stTabs [data-baseweb="tab"] { font-weight: 600; }
</style>
""", unsafe_allow_html=True)

model = CarbonModel()
sentinel = SentinelService()

# ---------------------------------------------------------------------------
# Sidebar — Inputs
# ---------------------------------------------------------------------------
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/2/27/Leaf_miner.jpg/320px-Leaf_miner.jpg",
             width=60, caption="")
    st.title("🌱 Carbon Tracker")
    st.caption("Estimación secuestro CO₂ agrícola · IPCC Tier 1")
    st.divider()

    st.subheader("📍 Parcela")
    input_mode = st.radio(
        "Modo entrada",
        ["Ref. catastral", "Coordenadas (demo)"],
        horizontal=True,
    )

    if input_mode == "Ref. catastral":
        ref_cat = st.text_input(
            "Referencia catastral",
            value="25120A00200001",
            help="14 caracteres. Ej: 25120A00200001 (Lleida)"
        )
        use_sigpac = st.button("🔍 Buscar parcela", type="primary")
    else:
        col1, col2 = st.columns(2)
        lat = col1.number_input("Lat", value=41.65, format="%.4f")
        lon = col2.number_input("Lon", value=0.93, format="%.4f")
        area_manual = st.number_input("Área (ha)", value=10.0, min_value=0.1)

    st.divider()
    st.subheader("🌾 Cultivo")
    crop_options = list(CROP_BIOMASS_REF.keys())
    crop_labels = {
        "wheat": "🌾 Trigo", "barley": "🌾 Cebada", "corn": "🌽 Maíz",
        "sunflower": "🌻 Girasol", "alfalfa": "🌿 Alfalfa",
        "vineyard": "🍇 Viñedo", "olive": "🫒 Olivo",
        "almond": "🌰 Almendro", "cover_crop": "🌱 Cubierta vegetal",
        "fallow": "⬜ Barbecho", "generic_annual": "📋 Cereal genérico",
    }
    crop_type = st.selectbox(
        "Tipo de cultivo",
        crop_options,
        format_func=lambda x: crop_labels.get(x, x),
        index=0,
    )

    ndvi_override = st.number_input(
        "NDVI medio anual (0-1)",
        min_value=0.0, max_value=1.0, value=0.45, step=0.01,
        help="Déjalo en 0 para usar referencia por cultivo"
    )
    ndvi_val = ndvi_override if ndvi_override > 0 else None

    st.divider()
    st.subheader("🚜 Prácticas agrícolas")
    tillage = st.select_slider(
        "Labranza",
        options=["conventional", "min_tillage", "no_till"],
        value="conventional",
        format_func=lambda x: {
            "conventional": "Convencional",
            "min_tillage": "Mínima",
            "no_till": "Sin labranza"
        }[x]
    )
    input_level = st.select_slider(
        "Gestión residuos",
        options=["low", "medium", "high", "high_manure"],
        value="medium",
        format_func=lambda x: {
            "low": "Baja", "medium": "Media",
            "high": "Alta (cubiertas)", "high_manure": "Alta + estiércol"
        }[x]
    )
    cover_crops = st.toggle("Cubiertas vegetales", value=False)
    climate_zone = st.selectbox(
        "Zona climática",
        ["warm_temperate_dry", "warm_temperate_moist",
         "cool_temperate_dry", "cool_temperate_moist"],
        format_func=lambda x: {
            "warm_temperate_dry": "Mediterráneo seco (Lleida, Zaragoza)",
            "warm_temperate_moist": "Mediterráneo húmedo (Costa)",
            "cool_temperate_dry": "Meseta norte",
            "cool_temperate_moist": "Galicia / Cantábrico",
        }[x]
    )

    st.divider()
    run_btn = st.button("⚡ Calcular CO₂", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Demo parcel data (used when SIGPAC unavailable)
# ---------------------------------------------------------------------------
DEMO_PARCEL = {
    "ref_catastral": "25120A00200001",
    "centroid": {"lat": 41.65, "lon": 0.93},
    "area_ha": 10.0,
    "uso_sigpac": "TA",
    "municipio": "Mollerussa",
    "provincia": "Lleida",
    "geometry": {
        "type": "Polygon",
        "coordinates": [[
            [0.928, 41.648], [0.932, 41.648],
            [0.932, 41.652], [0.928, 41.652],
            [0.928, 41.648],
        ]]
    }
}

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
if "parcel" not in st.session_state:
    st.session_state.parcel = DEMO_PARCEL
if "ndvi_series" not in st.session_state:
    # Generate mock NDVI for demo
    ndvi_df = sentinel.get_ndvi_series(
        {"west": 0.927, "south": 41.647, "east": 0.933, "north": 41.653},
        "2024-06-01", "2025-05-01"
    )
    st.session_state.ndvi_series = ndvi_df

# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------
st.title("🌱 Carbon Farming Tracker")
st.caption("Estimación de secuestro CO₂ agrícola · Metodología IPCC Tier 1 · Datos satélite Sentinel-2")

if run_btn or True:  # Always show content
    parcel = st.session_state.parcel
    if input_mode == "Coordenadas (demo)":
        parcel = {**DEMO_PARCEL,
                  "centroid": {"lat": lat, "lon": lon},
                  "area_ha": area_manual}

    # Compute carbon
    inputs = CarbonInputs(
        area_ha=parcel["area_ha"],
        crop_type=crop_type,
        tillage_practice=tillage,
        input_level=input_level,
        has_cover_crops=cover_crops,
        climate_zone=climate_zone,
        ndvi_mean=ndvi_val,
    )
    result = model.calculate(inputs)
    projection_df = model.project_3_years(
        inputs,
        {"tillage_practice": "no_till", "input_level": "high", "has_cover_crops": True}
    )

    # ---- Top KPI row ----
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🌍 CO₂e secuestrado", f"{result.total_co2e_t_yr:.1f} t/año",
              help="Toneladas CO₂ equivalente secuestradas por año")
    k2.metric("📐 Área parcela", f"{parcel['area_ha']:.1f} ha")
    k3.metric("⚗️ Confianza", result.confidence.upper(),
              delta=f"±{result.uncertainty_pct:.0f}%", delta_color="off")
    best_scenario = max(result.scenarios.items(), key=lambda x: x[1]["total_co2e_t_yr"])
    potential_gain = best_scenario[1]["total_co2e_t_yr"] - result.total_co2e_t_yr
    k4.metric("📈 Potencial mejora", f"+{potential_gain:.1f} t/año",
              help="Ganancia máxima con mejores prácticas")

    if result.warnings:
        warns = " · ".join(result.warnings)
        st.markdown(f'<div class="warning-box">⚠️ {warns}</div>', unsafe_allow_html=True)

    st.divider()

    # ---- Tabs ----
    tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Mapa", "📊 Dashboard CO₂", "📈 Proyección", "📄 Informe PDF"])

    # TAB 1 — Map
    with tab1:
        c1, c2 = st.columns([2, 1])
        with c1:
            clat = parcel["centroid"]["lat"]
            clon = parcel["centroid"]["lon"]
            m = folium.Map(location=[clat, clon], zoom_start=14,
                           tiles="Esri.WorldImagery")
            folium.GeoJson(
                parcel["geometry"],
                style_function=lambda x: {
                    "fillColor": "#52b788",
                    "color": "#2d6a4f",
                    "weight": 2,
                    "fillOpacity": 0.4,
                },
                tooltip=f"Área: {parcel['area_ha']:.1f} ha · CO₂: {result.total_co2e_t_yr:.1f} t/yr"
            ).add_to(m)
            folium.Marker(
                [clat, clon],
                popup=f"<b>{parcel.get('ref_catastral','')}</b><br>"
                      f"CO₂e: {result.total_co2e_t_yr:.1f} t/año<br>"
                      f"Cultivo: {crop_labels.get(crop_type, crop_type)}",
                icon=folium.Icon(color="green", icon="leaf", prefix="fa")
            ).add_to(m)
            st_folium(m, height=420, use_container_width=True)

        with c2:
            st.subheader("📋 Datos parcela")
            st.write(f"**Ref. catastral:** `{parcel.get('ref_catastral','demo')}`")
            st.write(f"**Municipio:** {parcel.get('municipio', 'N/A')}")
            st.write(f"**Provincia:** {parcel.get('provincia', 'Lleida')}")
            st.write(f"**Uso SIGPAC:** `{parcel.get('uso_sigpac', 'TA')}`")
            st.write(f"**Área:** {parcel['area_ha']:.2f} ha")
            st.divider()
            st.subheader("🛰️ NDVI Histórico")
            ndvi_df = st.session_state.ndvi_series
            if not ndvi_df.empty:
                chart_df = ndvi_df.set_index("date")["ndvi_mean"]
                st.line_chart(chart_df, color="#52b788")
                st.caption(f"NDVI medio anual: **{ndvi_df['ndvi_mean'].mean():.3f}**")

    # TAB 2 — CO2 Dashboard
    with tab2:
        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("🔬 Desglose carbono")
            breakdown_data = {
                "Componente": ["ΔSOC (suelo)", "Biomasa retenida"],
                "tC/año": [
                    result.delta_soc_total_tc_yr,
                    result.biomass_carbon_total_tc,
                ],
                "tCO₂e/año": [
                    round(result.delta_soc_total_tc_yr * 3.667, 3),
                    round(result.biomass_carbon_total_tc * 3.667, 3),
                ]
            }
            st.dataframe(pd.DataFrame(breakdown_data), hide_index=True, use_container_width=True)

            st.markdown(f"""
            <div class="metric-card">
                <div style="font-size:0.85rem;color:#555">TOTAL CO₂e secuestrado</div>
                <div class="co2-big">{result.total_co2e_t_yr:.2f}</div>
                <div style="font-size:0.85rem;color:#555">toneladas CO₂e / año</div>
                <div style="font-size:0.75rem;color:#888;margin-top:0.5rem">
                    Metodología: {result.methodology} · Incertidumbre: ±{result.uncertainty_pct:.0f}%
                </div>
            </div>
            """, unsafe_allow_html=True)

        with col_b:
            st.subheader("🔄 Comparativa prácticas")
            scenario_rows = []
            practice_labels = {
                "baseline_conventional": "Convencional",
                "min_tillage": "Labranza mínima",
                "cover_crops": "Cubiertas vegetales",
                "no_till_cover_crops": "No-till + cubiertas ★",
            }
            for k, v in result.scenarios.items():
                is_current = (
                    v["tillage"] == tillage and
                    v["input_level"] == input_level
                )
                scenario_rows.append({
                    "Práctica": ("→ " if is_current else "") + practice_labels.get(k, k),
                    "tCO₂e/año": v["total_co2e_t_yr"],
                    "vs actual": f"{v['total_co2e_t_yr'] - result.total_co2e_t_yr:+.2f}",
                })
            scen_df = pd.DataFrame(scenario_rows)
            st.dataframe(scen_df, hide_index=True, use_container_width=True)

            st.bar_chart(
                scen_df.set_index("Práctica")["tCO₂e/año"],
                color="#52b788",
            )

        st.divider()
        st.subheader("📐 Parámetros modelo")
        param_cols = st.columns(3)
        param_cols[0].metric("SOC referencia", f"{result.soc_ref_t_ha} tC/ha")
        param_cols[1].metric("SOC estimado", f"{result.soc_current_t_ha} tC/ha")
        param_cols[2].metric("Biomasa aérea", f"{result.ag_biomass_t_ha} tMS/ha")

    # TAB 3 — Projection
    with tab3:
        st.subheader("📈 Proyección 3 años: práctica actual vs no-till + cubiertas")
        st.caption("Año 1 = práctica actual. Año 2-3 = escenario mejorado (si se aplica cambio año 2).")

        pivot = projection_df.pivot(index="year", columns="scenario", values="co2e_t")
        st.bar_chart(pivot, color=["#a8dadc", "#2d6a4f"])

        st.dataframe(
            projection_df.rename(columns={
                "year": "Año", "scenario": "Escenario",
                "co2e_t": "CO₂e (t)", "soc_delta_tc": "ΔSOC (tC)",
                "biomass_tc": "Biomasa C (tC)"
            }),
            hide_index=True,
            use_container_width=True
        )

        if len(projection_df[projection_df["scenario"] == "improved"]) > 0:
            best_co2e = projection_df[projection_df["scenario"] == "improved"]["co2e_t"].max()
            current_co2e = projection_df[projection_df["scenario"] == "current"]["co2e_t"].iloc[0]
            gain = best_co2e - current_co2e
            st.success(f"✅ Cambio a no-till + cubiertas: **+{gain:.1f} tCO₂e/año** adicionales "
                       f"(+{gain/current_co2e*100:.0f}%)")

        st.divider()
        st.subheader("💶 Estimación valor mercado carbono voluntario")
        price_col, _ = st.columns([1, 2])
        price_eur = price_col.slider("Precio CO₂e (€/t)", 10, 80, 35,
                                     help="Mercado voluntario VCS/Gold Standard: 20-60€/t típico")
        revenue = result.total_co2e_t_yr * price_eur
        st.metric(f"Ingreso estimado a {price_eur}€/t",
                  f"{revenue:.0f} €/año",
                  help="Estimación indicativa. Precio real depende de certificación y comprador.")

    # TAB 4 — PDF
    with tab4:
        st.subheader("📄 Generar informe")
        st.info("El informe simula un certificado de secuestro CO₂ para presentación a compradores "
                "de créditos de carbono voluntarios.")

        farm_name = st.text_input("Nombre explotación", "Finca Demo Lleida")
        farmer_name = st.text_input("Titular", "Agricultor Demo")

        if st.button("📥 Generar PDF", type="primary"):
            with st.spinner("Generando informe..."):
                pdf_bytes = generate_pdf_report(
                    parcel=parcel,
                    result=result,
                    crop_type=crop_labels.get(crop_type, crop_type),
                    tillage=tillage,
                    ndvi_mean=ndvi_val,
                    projection_df=projection_df,
                    farm_name=farm_name,
                    farmer_name=farmer_name,
                )
                st.download_button(
                    label="⬇️ Descargar PDF",
                    data=pdf_bytes,
                    file_name=f"carbon_report_{parcel.get('ref_catastral','demo')}.pdf",
                    mime="application/pdf",
                )
                st.success("✅ Informe generado")

