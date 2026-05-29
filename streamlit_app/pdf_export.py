"""
PDF report generator — ReportLab
Simula certificado de secuestro CO₂ para mercado voluntario.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from io import BytesIO
from datetime import date
import pandas as pd


# Brand colors
GREEN_DARK = colors.HexColor("#2d6a4f")
GREEN_MID  = colors.HexColor("#52b788")
GREEN_LIGHT= colors.HexColor("#d8f3dc")
AMBER      = colors.HexColor("#ffc107")
GRAY       = colors.HexColor("#6c757d")
GRAY_LIGHT = colors.HexColor("#f8f9fa")


def generate_pdf_report(
    parcel: dict,
    result,
    crop_type: str,
    tillage: str,
    ndvi_mean,
    projection_df: pd.DataFrame,
    farm_name: str = "Explotación agrícola",
    farmer_name: str = "Titular",
) -> bytes:

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "Title", parent=styles["Title"],
        textColor=GREEN_DARK, fontSize=20, spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle", parent=styles["Normal"],
        textColor=GRAY, fontSize=10, spaceAfter=12, alignment=TA_CENTER,
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Heading2"],
        textColor=GREEN_DARK, fontSize=12, spaceBefore=14, spaceAfter=6,
        borderPad=4,
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=9, leading=14, spaceAfter=4,
    )
    disclaimer_style = ParagraphStyle(
        "Disclaimer", parent=styles["Normal"],
        fontSize=7.5, textColor=GRAY, leading=11,
    )

    story = []
    W = 17 * cm  # usable width

    # ---- HEADER ----
    story.append(Paragraph("🌱 Carbon Farming Tracker", title_style))
    story.append(Paragraph(
        "Informe de Estimación de Secuestro de Carbono Agrícola",
        ParagraphStyle("sub2", parent=subtitle_style, fontSize=12,
                       textColor=GREEN_DARK, alignment=TA_LEFT)
    ))
    story.append(HRFlowable(width=W, color=GREEN_DARK, thickness=2))
    story.append(Spacer(1, 6))

    # Report metadata
    meta_data = [
        ["Fecha emisión:", date.today().strftime("%d/%m/%Y"),
         "Metodología:", "IPCC 2006 GL Tier 1"],
        ["Explotación:", farm_name,
         "Titular:", farmer_name],
        ["Ref. catastral:", parcel.get("ref_catastral", "Demo"),
         "Municipio:", parcel.get("municipio", "Lleida")],
    ]
    meta_table = Table(meta_data, colWidths=[3.2*cm, 5.8*cm, 3.2*cm, 4.8*cm])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0,0), (-1,-1), colors.black),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [GRAY_LIGHT, colors.white]),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 12))

    # ---- RESULTADO PRINCIPAL ----
    story.append(Paragraph("1. Resultado Principal", section_style))

    main_result_data = [
        ["TOTAL CO₂e SECUESTRADO", f"{result.total_co2e_t_yr:.2f} tCO₂e/año"],
        ["Por hectárea", f"{result.total_co2e_t_yr/result.area_ha:.2f} tCO₂e/ha/año"],
        ["Área parcela", f"{result.area_ha:.2f} ha"],
        ["Nivel confianza", f"{result.confidence.upper()} (±{result.uncertainty_pct:.0f}%)"],
    ]
    main_table = Table(main_result_data, colWidths=[9*cm, 8*cm])
    main_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), GREEN_DARK),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 13),
        ("FONTNAME", (0,1), (-1,-1), "Helvetica"),
        ("FONTSIZE", (0,1), (-1,-1), 9),
        ("BACKGROUND", (0,1), (-1,-1), GREEN_LIGHT),
        ("GRID", (0,0), (-1,-1), 0.5, GREEN_MID),
        ("ALIGN", (1,0), (1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(main_table)
    story.append(Spacer(1, 10))

    # ---- PARCELA ----
    story.append(Paragraph("2. Datos de la Parcela", section_style))
    parcel_data = [
        ["Parámetro", "Valor"],
        ["Referencia catastral", parcel.get("ref_catastral", "N/A")],
        ["Municipio / Provincia", f"{parcel.get('municipio','N/A')} / {parcel.get('provincia','N/A')}"],
        ["Coordenadas centroide", f"Lat {parcel['centroid']['lat']:.4f}, Lon {parcel['centroid']['lon']:.4f}"],
        ["Área", f"{parcel['area_ha']:.2f} ha"],
        ["Uso SIGPAC", parcel.get("uso_sigpac", "TA")],
        ["Cultivo declarado", crop_type],
        ["NDVI medio anual", f"{ndvi_mean:.3f}" if ndvi_mean else "Referencia tabulada"],
    ]
    _styled_table(story, parcel_data, W)

    # ---- MODELO ----
    story.append(Paragraph("3. Parámetros del Modelo", section_style))
    tillage_labels = {"conventional": "Labranza convencional",
                      "min_tillage": "Labranza mínima", "no_till": "Sin labranza"}
    model_data = [
        ["Parámetro", "Valor", "Referencia"],
        ["Zona climática", "Mediterráneo seco (Warm Temperate Dry)", "IPCC Table 2.3"],
        ["SOC referencia", f"{result.soc_ref_t_ha} tC/ha (0-30cm)", "IPCC 2006 GL"],
        ["SOC estimado", f"{result.soc_current_t_ha} tC/ha", "F_lu × F_mg × F_i"],
        ["ΔSOC anual", f"{result.delta_soc_t_ha_yr:.4f} tC/ha/año", "Transición 20 años"],
        ["Práctica labranza", tillage_labels.get(tillage, tillage), "F_mg aplicado"],
        ["Biomasa aérea", f"{result.ag_biomass_t_ha} tMS/ha", "Ref. cultivo + NDVI"],
        ["Factor humificación", "kh = 0.15", "Panettieri et al. 2017"],
        ["Fracción carbono", "CF = 0.47", "IPCC default"],
        ["Conversión C→CO₂", "×3.667 (44/12)", "Estequiometría"],
    ]
    _styled_table(story, model_data, W, has_third_col=True)

    # ---- ESCENARIOS ----
    story.append(Paragraph("4. Comparativa de Prácticas Agrícolas", section_style))
    scen_data = [["Práctica", "tCO₂e/año", "ΔSOC tC/yr", "Biomasa tC"]]
    practice_labels = {
        "baseline_conventional": "Convencional",
        "min_tillage": "Labranza mínima",
        "cover_crops": "Cubiertas vegetales",
        "no_till_cover_crops": "No-till + cubiertas",
    }
    for k, v in result.scenarios.items():
        scen_data.append([
            practice_labels.get(k, k),
            f"{v['total_co2e_t_yr']:.2f}",
            f"{v['delta_soc_tc_yr']:.3f}",
            f"{v['biomass_carbon_tc']:.3f}",
        ])
    scen_table = Table(scen_data, colWidths=[7*cm, 3.5*cm, 3.5*cm, 3*cm])
    scen_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), GREEN_MID),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8.5),
        ("ALIGN", (1,0), (-1,-1), "CENTER"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, GREEN_LIGHT]),
        ("GRID", (0,0), (-1,-1), 0.5, GREEN_MID),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("BACKGROUND", (0,4), (-1,4), colors.HexColor("#b7e4c7")),  # highlight best
    ]))
    story.append(scen_table)
    story.append(Spacer(1, 6))

    # ---- PROYECCIÓN ----
    story.append(Paragraph("5. Proyección 3 Años", section_style))
    proj_data = [["Año", "Escenario", "CO₂e (t)", "ΔSOC (tC)", "Biomasa C (tC)"]]
    for _, row in projection_df.iterrows():
        proj_data.append([
            str(int(row["year"])),
            "Actual" if row["scenario"] == "current" else "Mejorado",
            f"{row['co2e_t']:.2f}",
            f"{row['soc_delta_tc']:.3f}",
            f"{row['biomass_tc']:.3f}",
        ])
    proj_table = Table(proj_data, colWidths=[2*cm, 4*cm, 3.5*cm, 3.5*cm, 4*cm])
    proj_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), GREEN_MID),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8.5),
        ("ALIGN", (2,0), (-1,-1), "CENTER"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, GREEN_LIGHT]),
        ("GRID", (0,0), (-1,-1), 0.5, GREEN_MID),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(proj_table)

    # ---- DISCLAIMER ----
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width=W, color=GRAY, thickness=0.5))
    story.append(Spacer(1, 6))
    disclaimer_text = (
        "<b>Aviso metodológico:</b> Este informe utiliza metodología IPCC 2006 Guidelines for National "
        "Greenhouse Gas Inventories, Tier 1 (datos tabulados por defecto). Las estimaciones presentadas "
        "tienen una incertidumbre inherente de ±30-50% al no incorporar análisis de suelo locales ni "
        "verificación de campo. No constituye un crédito de carbono certificado. Para certificación "
        "en mercados voluntarios (VCS, Gold Standard, C-SEAM) se requiere verificación por tercera "
        "parte acreditada. Este documento es exclusivamente de carácter informativo y orientativo."
    )
    story.append(Paragraph(disclaimer_text, disclaimer_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Generado por Carbon Farming Tracker · {date.today().strftime('%d/%m/%Y')} · "
        "Datos: Sentinel-2 (ESA/Copernicus), Open-Meteo, SIGPAC (FEGA)",
        ParagraphStyle("footer", parent=disclaimer_style, alignment=TA_RIGHT)
    ))

    doc.build(story)
    return buf.getvalue()


def _styled_table(story, data, width, has_third_col=False):
    if has_third_col:
        col_widths = [5*cm, 8*cm, 4*cm]
    else:
        col_widths = [6*cm, 11*cm]

    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), GREEN_MID),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8.5),
        ("FONTNAME", (0,1), (0,-1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, GREEN_LIGHT]),
        ("GRID", (0,0), (-1,-1), 0.5, GREEN_MID),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(table)
    story.append(Spacer(1, 6))
