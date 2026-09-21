"""
app.py — BESS Sizing & Engineering Analysis Platform

Streamlit front-end. All calculation logic lives in `core/` and
`export/` — this file only wires inputs to the engine and renders results.
"""

import json
import copy
import io
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.engine import default_config, compute_full_model, apply_override
from core.analyzer import run_scenario, system_impact_summary, sensitivity_sweep, compare_scenarios
from core.timeline import build_timeline
from core.validation import validate_augmentation_events
from export.excel_export import build_workbook

# --------------------------------------------------------------------------------------
# PAGE CONFIG + THEME
# --------------------------------------------------------------------------------------
st.set_page_config(
    page_title="BESS Engineering Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
:root {
    --bess-bg: #f4f7fb;
    --bess-panel: #ffffff;
    --bess-border: #dbe3ee;
    --bess-accent: #0891b2;
    --bess-accent-2: #0284c7;
    --bess-green: #16a34a;
    --bess-red: #dc2626;
    --bess-amber: #b45309;
    --bess-text: #0f172a;
    --bess-text-dim: #5b6b82;
}

html, body, [class*="css"]  { font-family: 'Inter', 'Segoe UI', sans-serif; }

/* App background */
.stApp {
    background: radial-gradient(1200px 600px at 10% -10%, #eef4fb 0%, #f4f7fb 45%, #f8fafc 100%);
}
.stApp, .stApp p, .stApp span, .stApp label, .stApp div { color: var(--bess-text); }

/* Sidebar */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #ffffff 0%, #eef4fb 100%);
    border-right: 1px solid var(--bess-border);
}
section[data-testid="stSidebar"] * { color: var(--bess-text) !important; }
section[data-testid="stSidebar"] .stRadio label {
    font-size: 0.95rem;
}

/* Headings */
h1, h2, h3 { color: var(--bess-text) !important; letter-spacing: 0.2px; }

/* KPI Card grid */
.kpi-card {
    background: linear-gradient(155deg, #ffffff 0%, #f7fafc 100%);
    border: 1px solid var(--bess-border);
    border-radius: 14px;
    padding: 16px 18px;
    box-shadow: 0 2px 10px rgba(15, 23, 42, 0.06);
    min-height: 108px;
}
.kpi-label {
    color: var(--bess-text-dim);
    font-size: 0.74rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 6px;
}
.kpi-value {
    color: var(--bess-text);
    font-size: 1.55rem;
    font-weight: 700;
}
.kpi-unit {
    color: var(--bess-accent);
    font-size: 0.85rem;
    font-weight: 600;
    margin-left: 4px;
}
.kpi-sub { color: var(--bess-text-dim); font-size: 0.75rem; margin-top: 4px; }

/* Status badges */
.badge {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.4px;
}
.badge-matched { background: rgba(22,163,74,0.12); color: #15803d; border: 1px solid rgba(22,163,74,0.35); }
.badge-notmatched { background: rgba(220,38,38,0.10); color: #b91c1c; border: 1px solid rgba(220,38,38,0.35); }
.badge-none { background: rgba(91,107,130,0.10); color: var(--bess-text-dim); border: 1px solid rgba(91,107,130,0.25); }

.section-title {
    color: var(--bess-text);
    font-size: 1.05rem;
    font-weight: 700;
    border-left: 4px solid var(--bess-accent);
    padding-left: 10px;
    margin: 6px 0 14px 0;
}

.warn-box {
    background: rgba(180, 83, 9, 0.08);
    border: 1px solid rgba(180, 83, 9, 0.30);
    border-radius: 10px;
    padding: 10px 14px;
    color: #92400e;
    font-size: 0.85rem;
    margin-bottom: 8px;
}
.err-box {
    background: rgba(220, 38, 38, 0.07);
    border: 1px solid rgba(220, 38, 38, 0.30);
    border-radius: 10px;
    padding: 10px 14px;
    color: #b91c1c;
    font-size: 0.85rem;
    margin-bottom: 8px;
}

.top-banner {
    background: linear-gradient(90deg, rgba(8,145,178,0.08), rgba(2,132,199,0.02));
    border: 1px solid rgba(8,145,178,0.25);
    border-radius: 16px;
    padding: 18px 24px;
    margin-bottom: 18px;
}

div[data-testid="stMetricValue"] { color: var(--bess-text); }
div[data-testid="stMetricLabel"] { color: var(--bess-text-dim); }

/* Tables / dataframes */
div[data-testid="stDataFrame"] { border: 1px solid var(--bess-border); border-radius: 10px; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

PLOTLY_TEMPLATE = "plotly_white"
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#0f172a"),
    margin=dict(l=10, r=10, t=42, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
)

# --------------------------------------------------------------------------------------
# SESSION STATE
# --------------------------------------------------------------------------------------
if "config" not in st.session_state:
    st.session_state.config = default_config()
if "project_name" not in st.session_state:
    st.session_state.project_name = "Untitled BESS Project"
if "change_log" not in st.session_state:
    st.session_state.change_log = []
if "scenario_preview" not in st.session_state:
    st.session_state.scenario_preview = None

AC_EFF_LABELS = {
    "lv_cable_eff": "LV / DC Cable Eff (%)",
    "pcs_eff": "PCS Eff (%)",
    "pcs_idt_eff": "PCS→IDT LV Cable Eff (%)",
    "idt_eff": "IDT Eff (%)",
    "dcdb_eff": "DC DB Eff (%)",
    "mv_eff": "MV Cable & Switchgear Eff (%)",
    "transformer_eff": "Main Transformer Eff (%)",
    "kv11_eff": "11kV Cable / IC Eff (%)",
    "measurement_acc": "Measurement Accuracy (%)",
}

WHATIF_PARAMS = {
    "DOD (all years)": "years.__all__.dod",
    "SOH (all years)": "years.__all__.soh",
    "Calendar Degradation (all years)": "years.__all__.calendar_degradation",
    "BESS Availability (all years)": "years.__all__.availability",
    "PCS Efficiency (all years)": "years.__all__.pcs_eff",
    "DC Discharge Efficiency (all years)": "years.__all__.dc_discharge_eff",
    "MV Cable & Switchgear Eff (all years)": "years.__all__.mv_eff",
    "Main Transformer Eff (all years)": "years.__all__.transformer_eff",
    "Measurement Accuracy (all years)": "years.__all__.measurement_acc",
    "DC-DC RTE (all years)": "years.__all__.dcdc_rte",
    "Container Count": "container.num_containers",
    "Aux Consumption / Container — Discharge (MW)": "container.aux_discharge_per_container_mw",
}


def kpi_card(label, value, unit="", sub=""):
    st.markdown(
        f"""<div class="kpi-card">
                <div class="kpi-label">{label}</div>
                <div class="kpi-value">{value}<span class="kpi-unit">{unit}</span></div>
                <div class="kpi-sub">{sub}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def status_badge(status_label):
    if status_label == "MATCHED":
        return '<span class="badge badge-matched">MATCHED</span>'
    if status_label == "NOT MATCHED":
        return '<span class="badge badge-notmatched">NOT MATCHED</span>'
    return '<span class="badge badge-none">NO REQUIREMENT</span>'


def year_options(cfg):
    return list(cfg["years"].keys())


def recompute():
    return compute_full_model(st.session_state.config)


# --------------------------------------------------------------------------------------
# SIDEBAR — NAVIGATION + PROJECT CONTROLS
# --------------------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚡ BESS Engineering Platform")
    st.caption("Sizing · Performance · Augmentation · What-If")
    st.session_state.project_name = st.text_input("Project name", st.session_state.project_name)

    nav = st.radio(
        "Navigate",
        [
            "🏠 Dashboard",
            "🛠️ Project Setup",
            "🗓️ Timeline (FAT/SAT)",
            "🔋 Discharge",
            "🔌 Charge",
            "🌀 Auxiliary",
            "📈 Augmentation",
            "✅ Requirement Matching",
            "♻️ RTE",
            "🧪 What-If Analysis",
            "🧠 Engineering Analyzer",
            "📤 Export",
        ],
        label_visibility="collapsed",
    )

    st.divider()
    st.markdown("**Project File**")
    colA, colB = st.columns(2)
    with colA:
        if st.button("↺ Reset", use_container_width=True):
            st.session_state.config = default_config()
            st.session_state.change_log = []
            st.rerun()
    with colB:
        cfg_json = json.dumps(st.session_state.config, indent=2)
        st.download_button("💾 Save", data=cfg_json, file_name="bess_project.json",
                            mime="application/json", use_container_width=True)

    uploaded = st.file_uploader("Load Project (.json)", type=["json"], label_visibility="collapsed")
    if uploaded is not None:
        try:
            loaded = json.load(uploaded)
            base = default_config()
            for key in ["container", "timeline", "auxiliary", "augmentation", "requirements"]:
                if key in loaded:
                    base[key] = loaded[key]
            if "years" in loaded:
                base["years"] = loaded["years"]
            else:
                n = base["timeline"]["num_years"]
                base["years"] = {f"Year {y}": base["years"].get(f"Year {y}", list(base["years"].values())[0])
                                  for y in range(1, n + 1)}
            if "project_name" in loaded:
                st.session_state.project_name = loaded["project_name"]
            st.session_state.config = base
            st.success("Project loaded.")
        except Exception as e:
            st.error(f"Could not load project: {e}")

# --------------------------------------------------------------------------------------
# RECOMPUTE (every rerun — this IS the "live recalculation" requirement)
# --------------------------------------------------------------------------------------
config = st.session_state.config
model = recompute()
year_table = model["year_table"]

# --------------------------------------------------------------------------------------
# TOP BANNER
# --------------------------------------------------------------------------------------
st.markdown(
    f"""<div class="top-banner">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
                <div style="color:#5b6b82; font-size:0.8rem; letter-spacing:1px; text-transform:uppercase;">Project</div>
                <div style="color:#0f172a; font-size:1.35rem; font-weight:700;">{st.session_state.project_name}</div>
            </div>
            <div style="text-align:right; color:#5b6b82; font-size:0.82rem;">
                {datetime.now().strftime("%d %b %Y, %H:%M")}<br/>
                {config['timeline']['num_years']}-Year Model
                {" · Augmentation Active" if config.get("augmentation", {}).get("enabled") else ""}
            </div>
        </div>
    </div>""",
    unsafe_allow_html=True,
)

if model["errors"]:
    for e in model["errors"]:
        st.markdown(f'<div class="err-box">⛔ {e}</div>', unsafe_allow_html=True)
if model["warnings"]:
    with st.expander(f"⚠️ {len(model['warnings'])} engineering unit-check warning(s)", expanded=False):
        for w in model["warnings"]:
            st.markdown(f'<div class="warn-box">⚠️ {w}</div>', unsafe_allow_html=True)

# ========================================================================================
# DASHBOARD
# ========================================================================================
if nav == "🏠 Dashboard":
    sel_year = st.selectbox("Dashboard Year", year_options(config), index=0)
    row = year_table[year_table["Year"] == sel_year].iloc[0]

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: kpi_card("Installed DC Capacity", f"{model['installed_dc_capacity']:,.1f}", "MWh")
    with c2: kpi_card("Containers (incl. Aug.)", f"{row['Containers']:.0f}", "Nos.")
    with c3: kpi_card("DC Guarantee Capacity", f"{row['DC Guarantee Capacity (MWh)']:.2f}", "MWh")
    with c4: kpi_card("POI Excl Aux (Discharge)", f"{row['POI Excl Aux - Discharge (MWh)']:.2f}", "MWh")
    with c5: kpi_card("POI Incl Aux (Discharge)", f"{row['POI Incl Aux - Discharge (MWh)']:.2f}", "MWh")

    c6, c7, c8, c9, c10 = st.columns(5)
    with c6: kpi_card("Discharge Time", f"{row['Discharge Time (h)']:.2f}", "h", f"C-rate {row['C-rate']:.3f}")
    with c7: kpi_card("Charge Guarantee (Incl Aux)", f"{row['Charge Guarantee Incl Aux (MWh)']:.2f}", "MWh")
    with c8: kpi_card("DC-DC RTE", f"{row['DC-DC RTE (%)']:.2f}", "%")
    with c9: kpi_card("AC RTE (Incl Aux)", f"{row['AC RTE Incl Aux (%)']:.2f}", "%")
    with c10:
        kpi_card("Total AC MV Energy", f"{row['Total AC MV Energy - Discharge (MWh)']:.2f}", "MWh",
                  "incl. augmentation" if config.get("augmentation", {}).get("enabled") else "")

    st.markdown(f"**Requirement status ({sel_year}):** {status_badge(row['Requirement Status'])}",
                unsafe_allow_html=True)

    st.markdown('<div class="section-title">Performance Over Project Life</div>', unsafe_allow_html=True)
    cc1, cc2 = st.columns(2)
    with cc1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=year_table["Year"], y=year_table["POI Excl Aux - Discharge (MWh)"],
                                  name="POI Excl Aux", line=dict(color="#38bdf8", width=3)))
        fig.add_trace(go.Scatter(x=year_table["Year"], y=year_table["POI Incl Aux - Discharge (MWh)"],
                                  name="POI Incl Aux", line=dict(color="#22d3ee", width=3, dash="dot")))
        if config.get("augmentation", {}).get("enabled"):
            fig.add_trace(go.Scatter(x=year_table["Year"], y=year_table["Total AC MV Energy - Discharge (MWh)"],
                                      name="Total AC MV Energy (incl. Aug.)", line=dict(color="#f59e0b", width=3)))
        fig.update_layout(title="POI Discharge Energy vs Year", template=PLOTLY_TEMPLATE, **PLOTLY_LAYOUT)
        st.plotly_chart(fig, use_container_width=True)
    with cc2:
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=year_table["Year"], y=year_table["AC RTE Excl Aux (%)"],
                                   name="AC RTE Excl Aux", line=dict(color="#a78bfa", width=3)))
        fig2.add_trace(go.Scatter(x=year_table["Year"], y=year_table["AC RTE Incl Aux (%)"],
                                   name="AC RTE Incl Aux", line=dict(color="#f472b6", width=3)))
        fig2.add_trace(go.Scatter(x=year_table["Year"], y=year_table["DC-DC RTE (%)"],
                                   name="DC-DC RTE", line=dict(color="#34d399", width=2, dash="dash")))
        fig2.update_layout(title="Round-Trip Efficiency vs Year", template=PLOTLY_TEMPLATE, **PLOTLY_LAYOUT)
        st.plotly_chart(fig2, use_container_width=True)

    cc3, cc4 = st.columns(2)
    with cc3:
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=year_table["Year"], y=year_table["SOH (%)"], name="SOH", line=dict(color="#38bdf8")))
        fig3.add_trace(go.Scatter(x=year_table["Year"], y=year_table["DOD (%)"], name="DOD", line=dict(color="#f59e0b")))
        fig3.add_trace(go.Scatter(x=year_table["Year"], y=year_table["Calendar Degradation (%)"],
                                   name="Calendar Degradation", line=dict(color="#f87171")))
        fig3.update_layout(title="Degradation Parameters vs Year", template=PLOTLY_TEMPLATE, **PLOTLY_LAYOUT)
        st.plotly_chart(fig3, use_container_width=True)
    with cc4:
        colors = ["#22c55e" if s == "MATCHED" else ("#ef4444" if s == "NOT MATCHED" else "#475569")
                  for s in year_table["Requirement Status"]]
        fig4 = go.Figure(go.Bar(x=year_table["Year"], y=year_table["Requirement Margin (MWh)"],
                                 marker_color=colors, name="Requirement Margin"))
        fig4.update_layout(title="Requirement Margin vs Year (Green = Matched)", template=PLOTLY_TEMPLATE, **PLOTLY_LAYOUT)
        st.plotly_chart(fig4, use_container_width=True)

    if config.get("augmentation", {}).get("enabled"):
        st.markdown('<div class="section-title">Augmentation</div>', unsafe_allow_html=True)
        fig5 = go.Figure()
        fig5.add_trace(go.Bar(x=year_table["Year"], y=year_table["Augmentation Energy (MWh)"],
                               name="Augmentation Energy", marker_color="#f59e0b"))
        fig5.add_trace(go.Scatter(x=year_table["Year"], y=year_table["Augmented Capacity (MWh)"],
                                   name="Cumulative Augmented Capacity", line=dict(color="#22d3ee", width=3),
                                   yaxis="y2"))
        fig5.update_layout(
            title="Augmented Energy & Cumulative Capacity vs Year",
            template=PLOTLY_TEMPLATE, **PLOTLY_LAYOUT,
            yaxis2=dict(overlaying="y", side="right", title="MWh (cumulative)"),
        )
        st.plotly_chart(fig5, use_container_width=True)

    st.markdown('<div class="section-title">Year-wise Performance Table</div>', unsafe_allow_html=True)
    st.dataframe(year_table, use_container_width=True, height=380)

# ========================================================================================
# PROJECT SETUP
# ========================================================================================
elif nav == "🛠️ Project Setup":
    st.markdown('<div class="section-title">Initial Inputs</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        config["container"]["dc_capacity_per_container"] = st.number_input(
            "DC installed capacity per container (MWh)",
            min_value=0.0, value=float(config["container"]["dc_capacity_per_container"]), step=0.1)
        config["container"]["num_containers"] = st.number_input(
            "Initial number of containers (Nos.)",
            min_value=1, value=int(config["container"]["num_containers"]), step=1)
        installed = config["container"]["dc_capacity_per_container"] * config["container"]["num_containers"]
        st.info(f"**Installed DC Capacity = {config['container']['dc_capacity_per_container']} × "
                f"{config['container']['num_containers']} = {installed:,.2f} MWh**")
    with c2:
        config["container"]["aux_discharge_per_container_mw"] = st.number_input(
            "Aux consumption / container — Discharge (MW)",
            min_value=0.0, value=float(config["container"]["aux_discharge_per_container_mw"]),
            step=0.001, format="%.4f")
        config["container"]["aux_charge_per_container_mw"] = st.number_input(
            "Aux consumption / container — Charge (MW)",
            min_value=0.0, value=float(config["container"]["aux_charge_per_container_mw"]),
            step=0.001, format="%.4f")

    st.markdown('<div class="section-title">Project Length</div>', unsafe_allow_html=True)
    new_num_years = st.number_input("Number of project years", min_value=1, max_value=30,
                                     value=int(config["timeline"]["num_years"]), step=1)
    if new_num_years != config["timeline"]["num_years"]:
        old_years = config["years"]
        template = list(old_years.values())[0] if old_years else None
        from core.engine import default_year_row
        new_years = {}
        new_reqs = {}
        for y in range(1, new_num_years + 1):
            label = f"Year {y}"
            new_years[label] = old_years.get(label, copy.deepcopy(template) if template else default_year_row())
            new_reqs[label] = config["requirements"].get(label, {"discharge_poi": None, "charge_poi": None})
        config["timeline"]["num_years"] = new_num_years
        config["years"] = new_years
        config["requirements"] = new_reqs
        st.rerun()

    st.caption("Guarantee discharge capacity at DC side is calculated automatically from these "
               "inputs on the Discharge tab — it is never entered manually.")

# ========================================================================================
# TIMELINE (FAT/SAT)
# ========================================================================================
elif nav == "🗓️ Timeline (FAT/SAT)":
    st.markdown('<div class="section-title">FAT / SAT</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        config["timeline"]["fat_required"] = st.toggle("FAT required?", value=config["timeline"]["fat_required"])
        if config["timeline"]["fat_required"]:
            config["timeline"]["fat_months"] = st.number_input(
                "FAT duration (months, max 6)", min_value=1, max_value=6,
                value=int(config["timeline"].get("fat_months", 1)))
    with c2:
        config["timeline"]["sat_required"] = st.toggle("SAT required?", value=config["timeline"]["sat_required"])
        if config["timeline"]["sat_required"]:
            config["timeline"]["sat_months"] = st.number_input(
                "SAT duration (months, max 6)", min_value=1, max_value=6,
                value=int(config["timeline"].get("sat_months", 1)))

    st.markdown('<div class="section-title">Project Timeline</div>', unsafe_allow_html=True)
    periods = build_timeline(config["timeline"])
    timeline_df = pd.DataFrame([
        {"Period": p["label"], "Type": p["type"],
         "Duration": f"{p.get('months', '')} month(s)" if p["type"] in ("FAT", "SAT") else "1 year"}
        for p in periods
    ])
    st.dataframe(timeline_df, use_container_width=True, hide_index=True)
    st.caption("FAT/SAT duration and calendar-effect treatment are user-supplied inputs only — "
               "no additional formulas are assumed beyond what you provide elsewhere in the model.")

# ========================================================================================
# DISCHARGE
# ========================================================================================
elif nav == "🔋 Discharge":
    st.markdown('<div class="section-title">Year-wise Discharge Parameters (DC + AC side)</div>',
                unsafe_allow_html=True)
    st.caption("Edit any cell — every dependent result (POI, RTE, requirement matching, charts, "
               "analyzer) recalculates immediately.")

    years = year_options(config)
    df_rows = []
    for y in years:
        r = config["years"][y]
        df_rows.append({
            "Year": y,
            "Availability (%)": r["availability"],
            "DC Discharge Eff (%)": r["dc_discharge_eff"],
            "SOH (%)": r["soh"],
            "Calendar Degradation (%)": r["calendar_degradation"],
            "DOD (%)": r["dod"],
            **{AC_EFF_LABELS[k]: r[k] for k in AC_EFF_LABELS},
            "Time Mode": r["time_mode"],
            "Discharge Time (h)": r["discharge_time"],
            "C-rate": r["c_rate"],
        })
    df = pd.DataFrame(df_rows)

    edited = st.data_editor(
        df, use_container_width=True, hide_index=True, height=420, key="discharge_editor",
        column_config={
            "Year": st.column_config.TextColumn(disabled=True),
            "Time Mode": st.column_config.SelectboxColumn(options=["time", "crate"]),
        },
    )

    for _, r in edited.iterrows():
        y = r["Year"]
        config["years"][y]["availability"] = float(r["Availability (%)"])
        config["years"][y]["dc_discharge_eff"] = float(r["DC Discharge Eff (%)"])
        config["years"][y]["soh"] = float(r["SOH (%)"])
        config["years"][y]["calendar_degradation"] = float(r["Calendar Degradation (%)"])
        config["years"][y]["dod"] = float(r["DOD (%)"])
        for k, label in AC_EFF_LABELS.items():
            config["years"][y][k] = float(r[label])
        config["years"][y]["time_mode"] = r["Time Mode"]
        config["years"][y]["discharge_time"] = float(r["Discharge Time (h)"])
        config["years"][y]["c_rate"] = float(r["C-rate"])

    model = recompute()
    year_table = model["year_table"]

    st.markdown('<div class="section-title">Calculated Discharge Results</div>', unsafe_allow_html=True)
    disc_cols = ["Year", "DC Guarantee Capacity (MWh)", "Discharge Time (h)", "C-rate",
                 "POI Excl Aux - Discharge (MWh)", "Aux Energy - Discharge (MWh)",
                 "POI Incl Aux - Discharge (MWh)"]
    st.dataframe(year_table[disc_cols], use_container_width=True, hide_index=True)

    with st.expander("🔍 Traceability — Year 1 discharge calculation breakdown"):
        y1 = years[0]
        d = model["discharge_detail"][y1]
        st.json({
            "formula_poi_excl": d["formula_poi_excl"],
            "ac_efficiency_factor": d["ac_efficiency_factor"],
            "poi_excl_aux_MWh": d["poi_excl_aux"],
            "aux_load_MW": d["aux_load_mw"],
            "discharge_time_h": d["discharge_time"],
            "aux_energy_MWh": d["aux_energy_mwh"],
            "formula_poi_incl": d["formula_poi_incl"],
            "poi_incl_aux_MWh": d["poi_incl_aux"],
        })

# ========================================================================================
# CHARGE
# ========================================================================================
elif nav == "🔌 Charge":
    st.markdown('<div class="section-title">Year-wise Charging Parameters</div>', unsafe_allow_html=True)
    st.caption("DC-DC RTE is fully independent, year by year — fixed or variable, your choice.")

    years = year_options(config)
    dcdc_mode = st.radio("DC-DC RTE mode", ["Fixed (apply to all years)", "Variable (per year)"], horizontal=True)
    if dcdc_mode.startswith("Fixed"):
        fixed_val = st.number_input("DC-DC RTE (%) — applied to all years",
                                     min_value=0.0, max_value=100.0,
                                     value=float(config["years"][years[0]]["dcdc_rte"]))
        if st.button("Apply fixed DC-DC RTE to all years"):
            for y in years:
                config["years"][y]["dcdc_rte"] = fixed_val
            st.rerun()

    df_rows = []
    for y in years:
        r = config["years"][y]
        df_rows.append({
            "Year": y,
            "DC Charging Eff (%)": r.get("dc_charge_eff", r["dc_discharge_eff"]),
            "Time Mode": r["time_mode"],
            "Charge Time (h)": r["charge_time"],
            "C-rate": r["c_rate"],
            "DC-DC RTE (%)": r["dcdc_rte"],
        })
    df = pd.DataFrame(df_rows)
    edited = st.data_editor(
        df, use_container_width=True, hide_index=True, height=420, key="charge_editor",
        column_config={
            "Year": st.column_config.TextColumn(disabled=True),
            "Time Mode": st.column_config.SelectboxColumn(options=["time", "crate"]),
        },
    )
    for _, r in edited.iterrows():
        y = r["Year"]
        config["years"][y]["dc_charge_eff"] = float(r["DC Charging Eff (%)"])
        config["years"][y]["time_mode"] = r["Time Mode"]
        config["years"][y]["charge_time"] = float(r["Charge Time (h)"])
        config["years"][y]["c_rate"] = float(r["C-rate"])
        config["years"][y]["dcdc_rte"] = float(r["DC-DC RTE (%)"])

    model = recompute()
    year_table = model["year_table"]

    st.markdown('<div class="section-title">Calculated Charging Results</div>', unsafe_allow_html=True)
    chg_cols = ["Year", "Charge Time (h)", "DC-DC RTE (%)",
                "Charge Guarantee Excl Aux (MWh)", "Charge Guarantee Incl Aux (MWh)"]
    st.dataframe(year_table[chg_cols], use_container_width=True, hide_index=True)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=year_table["Year"], y=year_table["Charge Guarantee Excl Aux (MWh)"],
                              name="Charge Guarantee Excl Aux", line=dict(color="#38bdf8", width=3)))
    fig.add_trace(go.Scatter(x=year_table["Year"], y=year_table["Charge Guarantee Incl Aux (MWh)"],
                              name="Charge Guarantee Incl Aux", line=dict(color="#f59e0b", width=3)))
    fig.update_layout(title="Charge Guarantee Capacity vs Year", template=PLOTLY_TEMPLATE, **PLOTLY_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)

# ========================================================================================
# AUXILIARY
# ========================================================================================
elif nav == "🌀 Auxiliary":
    st.markdown('<div class="section-title">Auxiliary Energy Module</div>', unsafe_allow_html=True)
    aux = config["auxiliary"]

    st.markdown("**Container Auxiliary** *(always active — computed from container count × per-container aux)*")
    st.caption(f"Discharge: {config['container']['num_containers']} × "
               f"{config['container']['aux_discharge_per_container_mw']} MW = "
               f"{config['container']['num_containers'] * config['container']['aux_discharge_per_container_mw']:.3f} MW")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Additional Auxiliary Consumption**")
        aux["additional_aux_enabled"] = st.toggle("Is there any additional auxiliary consumption?",
                                                    value=aux["additional_aux_enabled"])
        if aux["additional_aux_enabled"]:
            aux["additional_aux_value"] = st.number_input("Additional auxiliary (MWh / year)",
                                                            min_value=0.0, value=float(aux["additional_aux_value"]))
        else:
            aux["additional_aux_value"] = 0.0
    with c2:
        st.markdown("**Standby Energy**")
        aux["standby_enabled"] = st.toggle("Is standby energy applicable?", value=aux["standby_enabled"])
        if aux["standby_enabled"]:
            aux["standby_value"] = st.number_input("Standby energy (MWh / year)",
                                                     min_value=0.0, value=float(aux["standby_value"]))
        else:
            aux["standby_value"] = 0.0

    model = recompute()
    st.markdown('<div class="section-title">Year-wise Auxiliary Energy</div>', unsafe_allow_html=True)
    st.dataframe(model["year_table"][["Year", "Aux Energy - Discharge (MWh)"]],
                 use_container_width=True, hide_index=True)
    if model["warnings"]:
        st.markdown('<div class="warn-box">⚠️ Additional/standby auxiliary energy (MWh, direct) is summed with '
                    'Aux Load (MW) × Time (h). This combines two different measurement bases per the supplied '
                    'methodology — flagged, not altered.</div>', unsafe_allow_html=True)

# ========================================================================================
# AUGMENTATION
# ========================================================================================
elif nav == "📈 Augmentation":
    st.markdown('<div class="section-title">Augmentation</div>', unsafe_allow_html=True)
    aug = config["augmentation"]
    aug["enabled"] = st.toggle("Augmentation required?", value=aug["enabled"])

    if aug["enabled"]:
        c1, c2 = st.columns(2)
        with c1:
            aug["mismatch_losses"] = st.number_input("Mismatch Losses (%)", min_value=0.0, max_value=100.0,
                                                       value=float(aug.get("mismatch_losses", 99.0)))
        with c2:
            aug["ac_mv_power_to_plant_mw"] = st.number_input("AC MV Power to Plant Infrastructure (MW)",
                                                               min_value=0.0,
                                                               value=float(aug.get("ac_mv_power_to_plant_mw", 0.0)))

        st.markdown("**Augmentation Events** — specify year and number of containers added/replaced")
        events_df = pd.DataFrame(aug["events"]) if aug["events"] else pd.DataFrame(
            [{"year": 4, "containers": 10}])
        events_df = events_df.rename(columns={"year": "Year #", "containers": "Containers Added"})
        edited_events = st.data_editor(events_df, num_rows="dynamic", use_container_width=True,
                                        hide_index=True, key="aug_events_editor")
        new_events = []
        for _, r in edited_events.iterrows():
            if pd.notna(r.get("Year #")) and pd.notna(r.get("Containers Added")):
                new_events.append({"year": int(r["Year #"]), "containers": float(r["Containers Added"])})
        aug["events"] = new_events

        val = validate_augmentation_events(new_events, config["timeline"]["num_years"])
        for lvl, m in val:
            (st.error if lvl == "error" else st.warning)(m)

        model = recompute()
        year_table = model["year_table"]

        st.markdown('<div class="section-title">Augmentation Results</div>', unsafe_allow_html=True)
        aug_cols = ["Year", "Containers", "Augmented Capacity (MWh)", "Augmentation Energy (MWh)",
                    "Total AC MV Energy - Discharge (MWh)"]
        st.dataframe(year_table[aug_cols], use_container_width=True, hide_index=True)

        fig = go.Figure()
        fig.add_trace(go.Bar(x=year_table["Year"], y=year_table["Augmented Capacity (MWh)"],
                              name="Cumulative Augmented Capacity (MWh)", marker_color="#22d3ee"))
        fig.add_trace(go.Scatter(x=year_table["Year"], y=year_table["Total AC MV Energy - Discharge (MWh)"],
                                  name="Total AC MV Energy", line=dict(color="#f59e0b", width=3), yaxis="y2"))
        fig.update_layout(title="Augmentation Capacity & Total AC MV Energy vs Year",
                           template=PLOTLY_TEMPLATE, **PLOTLY_LAYOUT,
                           yaxis2=dict(overlaying="y", side="right"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Augmentation is disabled. Enable it above to open the full augmentation module "
                "(events, DC/AC losses, AC MV energy roll-up).")

# ========================================================================================
# REQUIREMENT MATCHING
# ========================================================================================
elif nav == "✅ Requirement Matching":
    st.markdown('<div class="section-title">Requirement Matching</div>', unsafe_allow_html=True)
    display_mode = st.radio("Status display", ["MATCHED / NOT MATCHED", "TRUE / FALSE"], horizontal=True)

    years = year_options(config)
    req_rows = []
    for y in years:
        req_rows.append({
            "Year": y,
            "Required Discharge POI (MWh)": config["requirements"].get(y, {}).get("discharge_poi"),
        })
    req_df = pd.DataFrame(req_rows)
    edited_req = st.data_editor(req_df, use_container_width=True, hide_index=True, key="req_editor",
                                 column_config={"Year": st.column_config.TextColumn(disabled=True)})
    for _, r in edited_req.iterrows():
        y = r["Year"]
        val = r["Required Discharge POI (MWh)"]
        config["requirements"].setdefault(y, {})["discharge_poi"] = (
            float(val) if pd.notna(val) else None
        )

    model = recompute()
    year_table = model["year_table"]

    st.markdown('<div class="section-title">Matching Results</div>', unsafe_allow_html=True)
    disp_df = year_table[["Year", "Required - Discharge POI (MWh)", "Total AC MV Energy - Discharge (MWh)",
                           "Requirement Status", "Requirement Margin (MWh)", "Requirement Margin (%)"]].copy()
    if display_mode == "TRUE / FALSE":
        disp_df["Requirement Status"] = disp_df["Requirement Status"].map(
            {"MATCHED": "TRUE", "NOT MATCHED": "FALSE", "NO REQUIREMENT": "—"})

    for _, r in disp_df.iterrows():
        cols = st.columns([1, 2, 2, 1.4, 1.6, 1.4])
        cols[0].write(r["Year"])
        cols[1].write(f"Req: {r['Required - Discharge POI (MWh)']}" if pd.notna(r['Required - Discharge POI (MWh)']) else "Req: —")
        cols[2].write(f"Calc: {r['Total AC MV Energy - Discharge (MWh)']:.2f} MWh")
        status_html = status_badge(year_table.loc[year_table['Year'] == r['Year'], 'Requirement Status'].iloc[0]) \
            if display_mode != "TRUE / FALSE" else f"**{r['Requirement Status']}**"
        cols[3].markdown(status_html, unsafe_allow_html=True)
        cols[4].write(f"Margin: {r['Requirement Margin (MWh)']:.2f}" if pd.notna(r['Requirement Margin (MWh)']) else "—")
        cols[5].write(f"{r['Requirement Margin (%)']:.1f}%" if pd.notna(r['Requirement Margin (%)']) else "—")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=year_table["Year"], y=year_table["Required - Discharge POI (MWh)"], name="Required"))
    fig.add_trace(go.Bar(x=year_table["Year"], y=year_table["Total AC MV Energy - Discharge (MWh)"], name="Calculated"))
    fig.update_layout(barmode="group", title="Required vs Calculated", template=PLOTLY_TEMPLATE, **PLOTLY_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)

# ========================================================================================
# RTE
# ========================================================================================
elif nav == "♻️ RTE":
    st.markdown('<div class="section-title">Round-Trip Efficiency</div>', unsafe_allow_html=True)
    st.dataframe(year_table[["Year", "DC-DC RTE (%)", "AC RTE Excl Aux (%)", "AC RTE Incl Aux (%)"]],
                 use_container_width=True, hide_index=True)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=year_table["Year"], y=year_table["DC-DC RTE (%)"], name="DC-DC RTE",
                              line=dict(color="#34d399", width=3)))
    fig.add_trace(go.Scatter(x=year_table["Year"], y=year_table["AC RTE Excl Aux (%)"], name="AC RTE Excl Aux",
                              line=dict(color="#38bdf8", width=3)))
    fig.add_trace(go.Scatter(x=year_table["Year"], y=year_table["AC RTE Incl Aux (%)"], name="AC RTE Incl Aux",
                              line=dict(color="#f472b6", width=3)))
    fig.update_layout(title="RTE vs Year", template=PLOTLY_TEMPLATE, **PLOTLY_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)

# ========================================================================================
# WHAT-IF ANALYSIS
# ========================================================================================
elif nav == "🧪 What-If Analysis":
    st.markdown('<div class="section-title">What-If Analysis</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        param_label = st.selectbox("Parameter", list(WHATIF_PARAMS.keys()))
    path = WHATIF_PARAMS[param_label]

    current_val = None
    if path.startswith("years.__all__"):
        field = path.split(".")[-1]
        current_val = config["years"][year_options(config)[0]][field]
    else:
        node = config
        for p in path.split(".")[:-1]:
            node = node[p]
        current_val = node[path.split(".")[-1]]

    with c2:
        st.metric("Current Value", f"{current_val}")
    with c3:
        new_val = st.number_input("New Value", value=float(current_val))

    b1, b2, b3 = st.columns(3)
    run_clicked = b1.button("▶ Run Scenario", use_container_width=True)
    apply_clicked = b2.button("✅ Apply Scenario", use_container_width=True)
    reset_clicked = b3.button("↺ Reset Scenario", use_container_width=True)

    if reset_clicked:
        st.session_state.scenario_preview = None
        st.rerun()

    if run_clicked:
        modified_config, base_result, scenario_result, diff = run_scenario(config, path, new_val)
        st.session_state.scenario_preview = {
            "path": path, "label": param_label, "before": current_val, "after": new_val,
            "modified_config": modified_config, "diff": diff,
        }

    if apply_clicked and st.session_state.scenario_preview:
        sp = st.session_state.scenario_preview
        st.session_state.config = sp["modified_config"]
        st.session_state.change_log.append({
            "parameter": sp["label"], "before": sp["before"], "after": sp["after"],
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        st.session_state.scenario_preview = None
        st.success("Scenario applied to base project.")
        st.rerun()

    if st.session_state.scenario_preview:
        sp = st.session_state.scenario_preview
        diff = sp["diff"]
        st.markdown(f"**Scenario:** {sp['label']}: `{sp['before']}` → `{sp['after']}`")

        summary = system_impact_summary(sp["label"], sp["before"], sp["after"], diff)
        s1, s2, s3 = st.columns(3)
        with s1:
            kpi_card("Avg. POI Incl Aux Δ", f"{summary['avg_poi_incl_aux_delta_mwh']:.2f}", "MWh")
        with s2:
            kpi_card("Avg. AC RTE Incl Aux Δ", f"{summary['avg_ac_rte_incl_aux_delta_pct']:.2f}", "%")
        with s3:
            flips = len(summary["years_flipped_to_not_matched"]) + len(summary["years_flipped_to_matched"])
            kpi_card("Requirement Status Flips", f"{flips}", "years")

        if summary["years_flipped_to_not_matched"]:
            st.markdown(f'<div class="err-box">⛔ Years newly NOT MATCHED: '
                        f'{", ".join(summary["years_flipped_to_not_matched"])}</div>', unsafe_allow_html=True)
        if summary["years_flipped_to_matched"]:
            st.markdown(f'<div class="warn-box">✅ Years newly MATCHED: '
                        f'{", ".join(summary["years_flipped_to_matched"])}</div>', unsafe_allow_html=True)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=diff["Year"], y=diff["POI Incl Aux - Discharge (MWh) (Before)"],
                                  name="POI Incl Aux — Before", line=dict(color="#38bdf8", width=2)))
        fig.add_trace(go.Scatter(x=diff["Year"], y=diff["POI Incl Aux - Discharge (MWh) (After)"],
                                  name="POI Incl Aux — After", line=dict(color="#f59e0b", width=3)))
        fig.update_layout(title="Before vs After — POI Incl Aux", template=PLOTLY_TEMPLATE, **PLOTLY_LAYOUT)
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Full year-wise before/after diff table"):
            st.dataframe(diff, use_container_width=True, hide_index=True)
    else:
        st.info("Set a new value and click **Run Scenario** to preview its impact "
                "before applying it to the base project.")

# ========================================================================================
# ENGINEERING ANALYZER
# ========================================================================================
elif nav == "🧠 Engineering Analyzer":
    tab1, tab2, tab3 = st.tabs(["📉 Sensitivity", "🆚 Scenario Comparison", "📜 Change Log"])

    with tab1:
        st.markdown('<div class="section-title">Parameter Sensitivity</div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        with c1:
            param_label = st.selectbox("Parameter to sweep", list(WHATIF_PARAMS.keys()), key="sens_param")
        with c2:
            target_year = st.selectbox("Target year", year_options(config), key="sens_year")
        with c3:
            target_col = st.selectbox("Target output", [
                "POI Incl Aux - Discharge (MWh)", "POI Excl Aux - Discharge (MWh)",
                "AC RTE Incl Aux (%)", "Charge Guarantee Incl Aux (MWh)",
            ], key="sens_col")

        path = WHATIF_PARAMS[param_label]
        base_val = config["years"][year_options(config)[0]][path.split(".")[-1]] if path.startswith("years.__all__") \
            else None
        lo = st.number_input("Sweep from", value=float(base_val) * 0.8 if base_val else 0.0)
        hi = st.number_input("Sweep to", value=float(base_val) * 1.05 if base_val else 100.0)
        steps = st.slider("Steps", 3, 15, 7)

        if st.button("Run Sensitivity Sweep"):
            values = [lo + (hi - lo) * i / (steps - 1) for i in range(steps)]
            sweep_df = sensitivity_sweep(config, path, values, target_year, target_col)
            fig = go.Figure(go.Scatter(x=sweep_df["Value"], y=sweep_df[target_col],
                                        mode="lines+markers", line=dict(color="#22d3ee", width=3)))
            fig.update_layout(title=f"{param_label} vs {target_col} ({target_year})",
                               template=PLOTLY_TEMPLATE, **PLOTLY_LAYOUT,
                               xaxis_title=param_label, yaxis_title=target_col)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(sweep_df, use_container_width=True, hide_index=True)

    with tab2:
        st.markdown('<div class="section-title">Scenario Comparison</div>', unsafe_allow_html=True)
        st.caption("Define up to 3 comparison cases against the current Base Case.")
        scenarios = {}
        for i in range(3):
            with st.expander(f"Case {chr(65+i)}", expanded=(i == 0)):
                enabled = st.checkbox(f"Enable Case {chr(65+i)}", key=f"case_en_{i}")
                if enabled:
                    p_label = st.selectbox("Parameter", list(WHATIF_PARAMS.keys()), key=f"case_param_{i}")
                    p_path = WHATIF_PARAMS[p_label]
                    p_val = st.number_input("New value", key=f"case_val_{i}", value=0.0)
                    scenarios[f"Case {chr(65+i)} — {p_label}"] = [(p_path, p_val)]
        if scenarios and st.button("Compare Scenarios"):
            comp_df = compare_scenarios(config, scenarios)
            st.dataframe(comp_df, use_container_width=True, hide_index=True)
            fig = go.Figure(go.Bar(x=comp_df["Scenario"], y=comp_df["Final-Year POI Incl Aux (MWh)"],
                                    marker_color="#38bdf8"))
            fig.update_layout(title="Final-Year POI Incl Aux by Scenario", template=PLOTLY_TEMPLATE, **PLOTLY_LAYOUT)
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.markdown('<div class="section-title">Engineering Change Log</div>', unsafe_allow_html=True)
        if st.session_state.change_log:
            log_df = pd.DataFrame(st.session_state.change_log)
            st.dataframe(log_df, use_container_width=True, hide_index=True)
        else:
            st.info("No scenarios have been applied to the base project yet. "
                    "Apply a What-If scenario to start the change log.")

# ========================================================================================
# EXPORT
# ========================================================================================
elif nav == "📤 Export":
    st.markdown('<div class="section-title">Excel Engineering Workbook</div>', unsafe_allow_html=True)
    st.caption("Generates a professional, auditable multi-sheet workbook: Executive Summary, "
               "Initial Inputs, FAT & SAT, Year-wise Base Calc, Discharging, Charging, Auxiliary "
               "Energy, Augmentation Schedule/Discharge/Charge, Requirement Matching (with "
               "green/red conditional formatting), RTE, Scenario Analysis and Engineering Analysis.")

    if st.button("🏗️ Build Workbook"):
        wb = build_workbook(model, config, project_name=st.session_state.project_name)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        st.session_state["_excel_bytes"] = buf.getvalue()
        st.success("Workbook built.")

    if "_excel_bytes" in st.session_state:
        st.download_button(
            "⬇️ Download Excel Workbook",
            data=st.session_state["_excel_bytes"],
            file_name=f"{st.session_state.project_name.replace(' ', '_')}_BESS_Engineering.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.markdown('<div class="section-title">Project JSON</div>', unsafe_allow_html=True)
    st.download_button("⬇️ Download Project JSON", data=json.dumps(config, indent=2),
                        file_name="bess_project.json", mime="application/json")
