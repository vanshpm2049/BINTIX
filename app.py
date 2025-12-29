# === Bintix Waste Analytics — CSV-only (All Variables Included) ===
# Variables: Tonnage, Trees_Saved, CO2_Kgs_Averted, Households_Participation_Percent, Segregation_Compliance_Percent
# CSV Upload Only Mode

import re
import io
import base64
import mimetypes
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import MarkerCluster, HeatMap
import plotly.express as px
import plotly.graph_objects as go
from matplotlib.ticker import FuncFormatter
import matplotlib.pyplot as plt
from matplotlib import colormaps
from branca.element import MacroElement, IFrame
from jinja2 import Template
import pydeck as pdk
from datetime import datetime

# ---------------- App & Brand ----------------
st.set_page_config(page_title="Bintix Waste Analytics", layout="wide")

BRAND_PRIMARY = 'purple'
TEXT_DARK = "#36204D"

# Speed settings
ST_MAP_HEIGHT = 900
ST_RETURNED_OBJECTS = []  # don't send all map layers back to Streamlit

# --- Environmental conversions ---
CO2_PER_KG_DRY = 2.18  # 1 kg dry waste -> 2.18 kg CO2 averted
KG_PER_TREE = 117.0     # 117 kg dry waste -> 1 tree saved

# ---------------- Assets (icons) ----------------
BASE_DIR = Path(__file__).parent.resolve()
_ASSET_DIR_CANDIDATES = [BASE_DIR / "assets", BASE_DIR / "assests"]
ASSETS_DIR = next((p for p in _ASSET_DIR_CANDIDATES if p.exists()), _ASSET_DIR_CANDIDATES[0])

@st.cache_resource(show_spinner=False)
def load_icon_data_uri(filename: str) -> str:
    """Return a data: URI for an image in ASSETS_DIR so it renders inside Folium popups."""
    p = ASSETS_DIR / filename
    if not p.exists():
        raise FileNotFoundError(f"Icon not found: {p}")
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"

try:
    TREE_ICON = load_icon_data_uri("tree.png")
    HOUSE_ICON = load_icon_data_uri("house.png")
    RECYCLE_ICON = load_icon_data_uri("waste-management.png")
    CO2_ICON = load_icon_data_uri("CO2.png")
except FileNotFoundError as e:
    st.warning(f"{e}\nUsing default markers instead.")
    TREE_ICON = HOUSE_ICON = RECYCLE_ICON = ""

# ---------------- Helper Functions ----------------
def create_trend_chart_base64(community_data, metric_name, color='purple'):
    """Create a small trend chart and return as base64 encoded PNG."""
    if community_data.empty:
        return None
    
    fig, ax = plt.subplots(figsize=(5, 3), dpi=80)
    ax.plot(community_data['Date'], community_data['Value'], marker='o', color=color, linewidth=2, markersize=4)
    ax.set_title(f'{metric_name} Trend', fontsize=10, fontweight='bold')
    ax.set_xlabel('Date', fontsize=8)
    ax.set_ylabel('Value', fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # Convert to base64
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    
    return img_base64

# ---------------- Data loading (CSV only - Upload Required) ----------------
# ALL variables from CSV
VARIABLES_REQUIRED = [
    "Tonnage",
    "Trees_Saved",
    "CO2_Kgs_Averted",
    "Households_Participation_Percent",
    "Segregation_Compliance_Percent"
]
ID_COLS_REQUIRED = ["City", "Community", "Pincode"]
ID_COLS_OPTIONAL = ["Latitude", "Longitude", "community_id"]



# --- Helpers for charts/popups (from PM.py) ---
def _to_data_uri(fig, w=340):
    buf = io.BytesIO()
    plt.tight_layout(pad=0.3)
    fig.savefig(buf, format="png", bbox_inches="tight", transparent=True, dpi=180)
    plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"<img src='data:image/png;base64,{b64}' style='width:{w}px;height:auto;border:0;'/>"


def _distinct_colors(n):
    cmaps = [plt.cm.tab20, plt.cm.Set3, plt.cm.Pastel1]
    colors = []
    i = 0
    while len(colors) < n:
        cmap = cmaps[i % len(cmaps)]
        M = cmap.N
        take = min(n - len(colors), M)
        for j in range(take):
            colors.append(cmap(j / max(M - 1, 1)))
        i += 1
    return colors[:n]
def tonnage_monthly_donut_base64(
    df_long: pd.DataFrame,
    city: str | None = None,
    community: str | None = None,
    width_px: int = 220
):
    d = df_long[df_long["Metric"] == "Tonnage"].copy()

    if city:
        d = d[d["City"] == str(city)]
    if community:
        d = d[d["Community"] == str(community)]

    if d.empty:
        return "<div style='color:#999;'>No tonnage data</div>"

    d["MonthKey"] = d["Date"].dt.to_period("M")
    monthly = (
        d.groupby("MonthKey", as_index=False)["Value"]
        .sum()
        .sort_values("MonthKey")
    )

    labels = [p.to_timestamp().strftime("%b %Y") for p in monthly["MonthKey"]]
    values = monthly["Value"].fillna(0).to_numpy()

    if values.sum() <= 0:
        return "<div style='color:#999;'>No tonnage recorded</div>"

    fig, ax = plt.subplots(figsize=(2.4, 2.4), dpi=140)
    colors = _distinct_colors(len(labels))

    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        autopct=lambda p: f"{p:.1f}%" if p > 0 else "",
        startangle=90,
        colors=colors,
        wedgeprops=dict(width=0.55, edgecolor="white", linewidth=1.2),
        pctdistance=0.75,
        labeldistance=1.05
    )

    ax.set(aspect="equal")
    ax.text(
        0, 0,
        "Tonnage\nShare",
        ha="center",
        va="center",
        fontsize=10,
        fontweight="bold",
        color=BRAND_PRIMARY
    )

    for autotext in autotexts:
        autotext.set_color("white")
        autotext.set_fontsize(7)
        autotext.set_weight("bold")

    for t in texts:
        t.set_fontsize(8)
        t.set_color(TEXT_DARK)

    buf = io.BytesIO()
    plt.tight_layout(pad=0.4)
    plt.savefig(buf, format="png", bbox_inches="tight", transparent=True)
    plt.close(fig)

    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"<img src='data:image/png;base64,{b64}' style='width:{width_px}px;height:auto;'/>"


# ============= ENHANCED POPUP FUNCTION (Image-Inspired Design) =============
def build_community_popup_html(row, tonnage_col, trees_col, co2_col, participation_col, 
                                compliance_col, community_id, TREE_ICON, HOUSE_ICON):
    """
    Build a styled popup HTML inspired by the design in image.jpg
    Features:
    - Community ID and metadata header
    - Icon-based stats (Trees Saved, Households)
    - Monthly CO2 Averted Donut Chart
    - KGs Trend Line Chart
    - Compliance percentage and segregation info
    """

    # Extract data safely
    try:
        community_name = str(row.get('Community', 'N/A'))
        city = str(row.get('City', 'N/A'))
        pincode = str(row.get('Pincode', 'N/A'))
        community_id_val = row.get('community_id', community_id)

        tonnage_val = float(row[tonnage_col]) if tonnage_col and pd.notna(row[tonnage_col]) else 0
        trees_val = float(row[trees_col]) if trees_col and pd.notna(row[trees_col]) else 0
        co2_val = float(row[co2_col]) if co2_col and pd.notna(row[co2_col]) else 0
        participation_val = float(row[participation_col]) if participation_col and pd.notna(row[participation_col]) else 0
        compliance_val = float(row[compliance_col]) if compliance_col and pd.notna(row[compliance_col]) else 0

        households = int(row.get('Households', 0)) if 'Households' in row else 0
    except:
        return "<div style='padding: 20px; color: #d9534f;'>Error loading data</div>"

    # Generate mini charts as base64
    # 1. CO2 Donut Chart
    co2_donut_img = ""
    try:
        # ---- Filter data for this community ----
        dco2 = df_long[
            (df_long["City"] == str(row["City"])) &
            (df_long["Community"] == str(row["Community"]))
        ].copy()

        if dco2.empty:
            raise ValueError("No data")

        # ---- Prefer actual CO2 metric, fallback to Tonnage → CO2 ----
        co2_metric = dco2[dco2["Metric"] == "CO2_Kgs_Averted"]

        if not co2_metric.empty:
            d = co2_metric.copy()
        else:
            # Fallback: derive CO2 from Tonnage
            ton = dco2[dco2["Metric"] == "Tonnage"].copy()
            if ton.empty:
                raise ValueError("No CO2 or Tonnage data")
            ton["Value"] = ton["Value"] * CO2_PER_KG_DRY
            d = ton

        # ---- Monthly aggregation ----
        d["MonthKey"] = d["Date"].dt.to_period("M")
        monthly = (
            d.groupby("MonthKey", as_index=False)["Value"]
            .sum()
            .sort_values("MonthKey")
        )

        if monthly["Value"].sum() <= 0:
            raise ValueError("No positive CO2 values")

        labels = [p.to_timestamp().strftime("%b") for p in monthly["MonthKey"]]
        values = monthly["Value"].to_numpy()

        colors_donut = _distinct_colors(len(labels))

        # ---- Plot donut ----
        fig, ax = plt.subplots(figsize=(2.5, 2.5), dpi=100)

        wedges, texts, autotexts = ax.pie(
            values,
            labels=labels,
            autopct=lambda pct: f"{pct:.1f}%" if pct > 0 else "",
            colors=colors_donut,
            wedgeprops=dict(width=0.55, edgecolor="white", linewidth=1.4),
            startangle=90,
            pctdistance=0.72,
            labeldistance=1.05
        )

        # Style labels
        for t in texts:
            t.set_fontsize(7)
            t.set_color("#36204D")
            t.set_weight("bold")

        for autotext in autotexts:
            autotext.set_color("white")
            autotext.set_weight("bold")
            autotext.set_fontsize(7)

        # Center text
        ax.text(
            0, 0,
            "CO₂\nAverted",
            ha="center",
            va="center",
            fontsize=11,
            color="#9b59b6",
            fontweight="bold"
        )

        ax.set(aspect="equal")
        plt.tight_layout(pad=0)

        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight", transparent=True)
        plt.close(fig)

        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        co2_donut_img = (
            f'<img src="data:image/png;base64,{b64}" '
            f'style="width:120px; height:120px;">'
        )

    except Exception:
        co2_donut_img = "<div style='color:#999;'>Chart unavailable</div>"

# 2. KGs Trend Chart (REAL DATA)
    kg_trend_img = ""
    try:
        # ---- Filter monthly tonnage for this community ----
        dkg = df_long[
            (df_long["City"] == str(row["City"])) &
            (df_long["Community"] == str(row["Community"])) &
            (df_long["Metric"] == "Tonnage")
        ].copy()

        if dkg.empty:
            raise ValueError("No tonnage data")

        # Month aggregation
        dkg["MonthKey"] = dkg["Date"].dt.to_period("M")
        monthly = (
            dkg.groupby("MonthKey", as_index=False)["Value"]
            .sum()
            .sort_values("MonthKey")
        )

        months_full = [p.to_timestamp().strftime("%b") for p in monthly["MonthKey"]]
        kg_values = monthly["Value"].fillna(0).tolist()

        # ---- Plot ----
        fig, ax = plt.subplots(figsize=(6, 2.7), dpi=100)

        ax.plot(
            months_full,
            kg_values,
            marker='o',
            color='#8b4789',
            linewidth=2.5,
            markersize=5
        )

        ax.fill_between(
            range(len(kg_values)),
            kg_values,
            alpha=0.12,
            color='#8b4789'
        )

        ax.set_ylabel('KGs', fontsize=9, color='#8b4789', fontweight='bold')
        ax.set_xlabel('')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color("#000000")
        ax.spines['bottom'].set_color("#000000")
        ax.grid(True, alpha=0.2, axis='y')
        ax.tick_params(labelsize=8, colors="#000000")

        plt.xticks(rotation=45, ha='right')
        plt.tight_layout(pad=0.5)

        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', transparent=True)
        plt.close(fig)

        b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        kg_trend_img = (
            f'<img src="data:image/png;base64,{b64}" '
            f'style="width:150%; height:auto; max-width:320px;">'
        )

    except Exception:
        kg_trend_img = "<div style='color:#999;'>Trend chart unavailable</div>"
    # Trees saved calculation
    trees_saved = int(co2_val / 21) if co2_val and co2_val > 0 else 0
    uid = f"p_{str(row['Community']).replace(' ','_')}_{row['Pincode']}"
    popup_html = f"""
    <style>
    @keyframes fadeUp {{
        from {{ opacity:0; transform:translateY(10px); }}
        to {{ opacity:1; transform:translateY(0); }}
    }}
    @keyframes scaleIn {{
        from {{ transform:scale(0.85); opacity:0; }}
        to {{ transform:scale(1); opacity:1; }}
    }}
    @keyframes ringPulse {{
        0% {{ transform:scale(1); opacity:0.6; }}
        100% {{ transform:scale(1.3); opacity:0; }}
    }}
    @keyframes iconPop {{
        0% {{ transform:scale(0.6); opacity:0; }}
        60% {{ transform:scale(1.25); opacity:1; }}
        100% {{ transform:scale(1); }}
    }}

    .anim {{ animation: fadeUp 0.6s ease forwards; }}
    .scale {{ animation: scaleIn 0.6s ease forwards; }}
    .icon-anim {{ animation: iconPop 0.9s cubic-bezier(0.2,0.9,0.3,1) forwards; }}

    /* PERFORMANCE COLORS */
    .perf-low  {{ --glow: rgba(220,53,69,0.55); }}
    .perf-mid  {{ --glow: rgba(255,193,7,0.55); }}
    .perf-high {{ --glow: rgba(0,166,81,0.55); }}

    /* IMPACT CARD */
    .donut-wrap {{
        position: relative;
        transition: transform 0.35s ease, filter 0.35s ease;
    }}
    .donut-wrap:hover {{
        transform: scale(1.06);
        filter: drop-shadow(0 0 14px var(--glow))
                drop-shadow(0 0 26px var(--glow));
    }}
    .donut-wrap::after {{
        content:"";
        position:absolute;
        inset:-6px;
        border-radius:16px;
        border:2px solid var(--glow);
        opacity:0;
    }}
    .donut-wrap:hover::after {{
        animation: ringPulse 0.9s ease-out infinite;
    }}

    /* MODALS */
    .modal-bg {{
        position:fixed;
        inset:0;
        background:rgba(0,0,0,0.55);
        display:none;
        align-items:center;
        justify-content:center;
        z-index:9999;
    }}
    .modal {{
        background:#fff;
        border-radius:12px;
        padding:16px 18px;
        width:280px;
        font-family:Poppins;
        box-shadow:0 8px 30px rgba(0,0,0,0.25);
        animation: scaleIn 0.3s ease;
    }}
    .modal p {{ font-size:13px; margin:4px 0; }}

    /* TREND */
    .trend-wrap {{ cursor: zoom-in; }}
    .trend-wrap img {{
        transition: transform 0.35s ease, filter 0.35s ease;
    }}
    .trend-wrap:hover img {{
        transform: scale(1.04);
        filter: drop-shadow(0 0 14px rgba(0,0,0,0.3));
    }}
    .trend-modal {{
        background:#fff;
        border-radius:14px;
        padding:14px;
        max-width:90vw;
        max-height:90vh;
        animation: scaleIn 0.3s ease;
        position: relative;
    }}
    .close-btn {{
        position:absolute;
        top:8px;
        right:12px;
        font-size:18px;
        cursor:pointer;
    }}
    </style>

    <div style="font-family:Poppins; width:440px; padding:10px;">

    <!-- TOP ROW -->
    <div style="display:flex; justify-content:space-between; align-items:flex-start;">

        <!-- LEFT INFO -->
        <div style="width:55%;" class="anim">
            <div style="font-size:22px; font-weight:700; color:{BRAND_PRIMARY};">
                {row["Community"]}
            </div>
            <div style="font-size:12px; color:#666;">
                {row["City"]} · {row["Pincode"]}
            </div>

            <div style="margin-top:10px; font-size:14px; line-height:2;">
                <div><b>Total Waste:</b> <span id="{uid}_ton">0</span> kg</div>
                <div><b>Participation:</b> <span id="{uid}_part">0</span>%</div>
            </div>
        </div>

        <!-- ICON IMPACT PANEL -->
        <div style="width:45%; display:flex; justify-content:center;" class="scale">
            <div class="donut-wrap perf-{'high' if participation_val >= 70 else 'mid' if participation_val >= 40 else 'low'}"
                style="width:180px; padding:16px; border-radius:14px; background:#fafafa; text-align:center;">

                <div style="margin-bottom:18px;">
                    <img id="{uid}_tree_icon" src="{TREE_ICON}" style="width:56px; height:56px;"/>
                    <div style="font-size:18px; font-weight:700;">
                        <span id="{uid}_tree">0</span>
                    </div>
                    <div style="font-size:12px; color:#666;">Trees Saved</div>
                </div>

                <div>
                    <img id="{uid}_co2_icon" src="{CO2_ICON}" style="width:60px; height:60px;"/>
                    <div style="font-size:16px; font-weight:700;">
                        <span id="{uid}_co2">0</span> kg
                    </div>
                    <div style="font-size:12px; color:#666;">CO₂ Averted</div>
                </div>

            </div>
        </div>
    </div>

    <!-- TREND -->
    <div style="margin-top:14px; text-align:center;" class="anim">
        <div style="font-weight:600; font-size:13px; color:{BRAND_PRIMARY}; margin-bottom:6px;">
            Monthly Waste Trend
        </div>
        <div class="trend-wrap" onclick="openTrendModal_{uid}()">
            {kg_trend_img}
        </div>
    </div>

    <!-- TREND MODAL -->
    <div class="modal-bg" id="trend_modal_{uid}" onclick="closeTrendModal_{uid}()">
        <div class="trend-modal" onclick="event.stopPropagation()">
            <div class="close-btn" onclick="closeTrendModal_{uid}()">✕</div>
            {kg_trend_img}
        </div>
    </div>

    </div>

    <script>
    (function() {{
    function animate(id, end) {{
        const el = document.getElementById(id);
        if(!el) return;
        const start = performance.now();
        const dur = 800;
        function step(t) {{
            const p = Math.min((t-start)/dur,1);
            el.innerText = Math.floor(p*end).toLocaleString();
            if(p<1) requestAnimationFrame(step);
        }}
        requestAnimationFrame(step);
    }}

    animate("{uid}_ton", {int(tonnage_val)});
    animate("{uid}_part", {participation_val});
    animate("{uid}_tree", {trees_saved});
    animate("{uid}_co2", {int(co2_val)});

    document.getElementById("{uid}_tree_icon")?.classList.add("icon-anim");
    document.getElementById("{uid}_co2_icon")?.classList.add("icon-anim");
    }})();

    function openTrendModal_{uid}() {{
        document.getElementById("trend_modal_{uid}").style.display="flex";
    }}
    function closeTrendModal_{uid}() {{
        document.getElementById("trend_modal_{uid}").style.display="none";
    }}
    </script>
    """


    return popup_html
def popup_charts_for_comm(dfl_filtered: pd.DataFrame, community_id: str):
    BRAND = BRAND_PRIMARY
    dm = dfl_filtered.copy()
    dm["Community"] = dm["Community"].astype(str)
    dm = dm[dm["Community"] == str(community_id)]
    if dm.empty:
        return "", ""

    dm["MonthKey"] = dm["Date"].dt.to_period("M")

    # ------------------ TONNAGE (Plotly static PNG for popup) ------------------
    import plotly.express as px
    import plotly.io as pio

    bar_img = ""
    d_ton = dm[dm["Metric"] == "Tonnage"][["MonthKey", "Value"]].copy()
    if not d_ton.empty:
        d_ton["MonthLabel"] = [period.to_timestamp().strftime("%b") for period in d_ton["MonthKey"]]
        fig, ax = plt.subplots(figsize=(4.0, 1.4), dpi=120)
        ax.plot(d_ton["MonthLabel"], d_ton["Value"], marker="o", lw=1.6, color=BRAND)
        ax.spines["right"].set_visible(False)
        ax.spines["top"].set_visible(False)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{int(v):,}"))
        ax.tick_params(axis="x", labelsize=8, colors=BRAND)
        ax.tick_params(axis="y", labelsize=8, colors=BRAND)
        ax.grid(alpha=0.12, axis="y")
        plt.xticks(rotation=45)
        bar_img = _to_data_uri(fig, w=380)


            

    # ------------------ CO2 DONUT (Plotly interactive preferred) ------------------
    # ------------------ CO2 DONUT (matplotlib with values) ------------------
    donut_img = ""
    dry_candidates = ["Tonnage_Dry", "Dry_Tonnage", "DryWaste", "Tonnage"]
    dry_month = None
    for m in dry_candidates:
        cur = dm[dm["Metric"] == m][["MonthKey", "Value"]].copy()
        if not cur.empty:
            cur["Value"] = pd.to_numeric(cur["Value"], errors="coerce").fillna(0.0)
            dry_month = cur
            break




    if dry_month is not None:
        d = dry_month.groupby("MonthKey", as_index=False)["Value"].sum().sort_values("MonthKey")
        co2_vals = (d["Value"] * CO2_PER_KG_DRY).clip(lower=0.0).to_numpy()
        labels = [p.to_timestamp().strftime("%b") for p in d["MonthKey"]]
        colors = _distinct_colors(len(labels))

        # --- Donut chart with slice labels ---
        fig, ax = plt.subplots(figsize=(2.3, 2.3), dpi=120)
        wedges, texts, autotexts = ax.pie(
            co2_vals,
            labels=labels,  # ✅ show month beside slice
            autopct=lambda pct: (f'{pct:.1f}%') if pct > 0 else '',
            wedgeprops=dict(width=0.60, edgecolor='white', linewidth=1.2),
            startangle=90,
            colors=colors,
            pctdistance=0.7,
            labeldistance=1.05  # slight spacing between label and slice
        )
        ax.set(aspect="equal")

        # Format labels & percentages
        for t in texts:
            t.set_fontsize(8)
            t.set_color("#36204D")
            t.set_weight("bold")

        from matplotlib.colors import to_rgb
        for wedge, autotext in zip(wedges, autotexts):
            r, g, b = wedge.get_facecolor()[:3]
            lum = 0.2126*r + 0.7152*g + 0.0722*b
            autotext.set_color('#ffffff' if lum < 0.6 else '#222222')
            autotext.set_fontsize(8)
            autotext.set_weight('bold')

        # Center text inside donut
        ax.text(0, 0, "CO₂\nAverted", ha="center", va="center",
                fontsize=10, color='purple', fontweight="bold")

        plt.tight_layout(pad=0.3)
        donut_img = _to_data_uri(fig, w=200)
        plt.close(fig)

        # --- Legend below the donut ---
        

        
        donut_img = f"<div style='text-align:center;'>{donut_img}</div>"
    # return HTML fragments (bar_img and donut_img)
    return bar_img, donut_img

def normalize_column_names(df):
    """
    Normalize column names to match expected format:
    - 'Tonnage Apr 2025' -> 'Tonnage_2025-04'
    - 'Trees Saved May 2025' -> 'Trees_Saved_2025-05'
    - 'Households Participation % Jun 2025' -> 'Households_Participation_Percent_2025-06'
    """
    month_map = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
    }
    
    new_cols = {}
    for col in df.columns:
        # Check if column matches pattern: "Metric Month Year"
        # e.g., "Tonnage Apr 2025" or "Trees Saved Apr 2025" or "Households Participation % Apr 2025"
        pattern = r'^(.+?)\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})$'
        match = re.match(pattern, col, re.IGNORECASE)
        
        if match:
            metric_raw = match.group(1).strip()
            month_abbr = match.group(2).capitalize()
            year = match.group(3)
            
            # Normalize metric name
            metric_normalized = metric_raw.replace(' ', '_').replace('%', 'Percent')
            
            # Build new column name: Metric_YYYY-MM
            month_num = month_map.get(month_abbr, '01')
            new_col = f"{metric_normalized}_{year}-{month_num}"
            new_cols[col] = new_col
    
    if new_cols:
        df = df.rename(columns=new_cols)
    
    return df

# Regex to detect metric_YYYY-MM columns
METRIC_COL_REGEX = re.compile(
    r"^(Tonnage|Trees_Saved|CO2_Kgs_Averted|Households_Participation_Percent|Segregation_Compliance_Percent)_(\d{4}-\d{2})$"
)

def _detect_metric_month_cols(columns):
    cols, months = [], set()
    for c in columns:
        m = METRIC_COL_REGEX.match(c)
        if m:
            cols.append(c)
            months.add(m.group(2))
    return cols, sorted(months)

@st.cache_data(show_spinner=False)
def load_uploaded(file) -> tuple[pd.DataFrame, pd.DataFrame, list[str], str]:
    df = pd.read_csv(file)
    df.rename(columns={c: c.strip() for c in df.columns}, inplace=True)
    
    # Normalize column names from "Metric Month Year" to "Metric_YYYY-MM"
    df = normalize_column_names(df)
    
    # Check required ID columns
    missing = [c for c in ID_COLS_REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    # Detect metric-month columns
    metric_month_cols, months = _detect_metric_month_cols(df.columns)
    if not metric_month_cols:
        raise ValueError(
            f"No metric-month columns found. Expected format: {{Metric}}_YYYY-MM\n"
            f"Supported metrics: {', '.join(VARIABLES_REQUIRED)}"
        )
    
    # Convert metric columns to numeric
    for c in metric_month_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    
    # Identify all ID columns present
    id_cols_present = [c for c in (ID_COLS_REQUIRED + ID_COLS_OPTIONAL) if c in df.columns]
    
    # Melt to long format
    long_df = df.melt(
        id_vars=id_cols_present,
        value_vars=metric_month_cols,
        var_name="Metric_Month",
        value_name="Value"
    )
    
    # Split Metric_Month into Metric and Date
    parts = long_df["Metric_Month"].str.rsplit("_", n=1, expand=True)
    long_df["Metric"] = parts[0]
    long_df["Date"] = pd.to_datetime(parts[1] + "-01", format="%Y-%m-%d")
    long_df = long_df.drop(columns=["Metric_Month"]).sort_values(
        id_cols_present + ["Metric", "Date"]
    )
    
    # Convert string columns
    for c in ["City", "Community", "Pincode"]:
        if c in df.columns:
            df[c] = df[c].astype(str)
        if c in long_df.columns:
            long_df[c] = long_df[c].astype(str)
    
    # Convert numeric columns
    for c in ["Latitude", "Longitude"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    
    return df, long_df, months, f"uploaded: {file.name}"

# ---------------- Sidebar (Upload Only) ----------------
with st.sidebar:
    st.markdown("### 📤 Upload Your Data")
    uploaded = st.file_uploader(
        "Upload CSV File",
        type=["csv"],
        help=(
            "Required columns: City, Community, Pincode, Latitude, Longitude\n"
            "Metric columns format: 'Metric Month Year' (e.g., 'Tonnage Apr 2025')\n\n"
            "Supported Metrics:\n"
            "• Tonnage\n"
            "• Trees Saved\n"
            "• CO2 Kgs Averted\n"
            "• Households Participation %\n"
            "• Segregation Compliance %"
        )
    )
    
    if uploaded is None:
        st.warning("⚠️ Please upload a CSV file to proceed.")
    
    st.markdown("---")
    st.markdown("### 🗺️ Map Type")
    map_type = st.radio(
        "Select Map Type",
        options=["2D Map (Folium)", "3D Map (PyDeck)"],
        index=0,
        help="Choose between 2D interactive map or 3D extruded visualization"
    )
    
    st.markdown("---")
    
    # Only show these options for 2D map
    if map_type == "2D Map (Folium)":
        st.caption("Map heatmap options:")
        heatmap_metric = st.selectbox(
            "Heatmap by",
            options=["None", "Tonnage", "Trees Saved", "CO2 Kgs Averted", 
                    "Households Participation %", "Segregation Compliance %"],
            index=0,
            help="Show colored markers by selected metric",
            key="heatmap_metric"
        )
    else:
        # For 3D map
        show_popup_charts = True  # Not applicable for 3D
        heatmap_metric = "None"
        
        extrude_metric = st.selectbox(
            "Extrude by",
            options=["Tonnage", "Trees Saved", "CO2 Kgs Averted", 
                    "Households Participation %", "Segregation Compliance %"],
            index=0,
            help="Height of 3D columns represents this metric",
            key="extrude_metric"
        )

# Check if file is uploaded
if uploaded is None:
    st.error("📁 Please upload a CSV file to get started. Use the upload widget on the left sidebar.")
    st.stop()

# Try to load the uploaded file
try:
    df_wide, df_long, months, data_src = load_uploaded(uploaded)
    st.session_state["df_wide"] = df_wide
    st.session_state["df_long"] = df_long
    st.session_state["months"] = months
    st.session_state["data_src"] = data_src
except Exception as e:
    st.error(f"❌ Error loading dataset: {e}")
    st.stop()

# Minor UI theming
st.markdown(
    """
    <style>
    .main { background-color: #f9f9f9; }
    h1, h2, h3 { color: #36204D; }
    /* Hide the multiselect labels when all items are selected */
    div[data-baseweb="select"] span[data-baseweb="tag"] {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Load Data from session
df_wide = st.session_state["df_wide"]
df_long = st.session_state["df_long"]
months = st.session_state["months"]
data_src = st.session_state["data_src"]

# Normalize key id columns to STRING (safety)
for col in ["Pincode", "Community", "City"]:
    if col in df_wide.columns:
        df_wide[col] = df_wide[col].astype(str)
    if col in df_long.columns:
        df_long[col] = df_long[col].astype(str)

# Title
st.markdown(
    f"""
    <h1 style='text-align:center; color:{BRAND_PRIMARY};'>
    ♻️ Bintix Waste Analytics Dashboard
    </h1>
    <p style='text-align:center; color:gray;'>CSV Upload Mode — All Metrics Included</p>
    """,
    unsafe_allow_html=True
)

# ---------------- Filter Controls ----------------
st.markdown("### 🔍 Filters")
col_f1, col_f2, col_f3 = st.columns(3)

with col_f1:
    cities_all = sorted(df_wide["City"].dropna().unique())
    
    # Initialize filter state if not exists
    if "city_filter_initialized" not in st.session_state:
        st.session_state.city_filter_initialized = True
        st.session_state.city_selection = cities_all  # All selected by default
    
    city_filter = st.multiselect(
        "Select City/Cities", 
        cities_all, 
        default=st.session_state.city_selection if st.session_state.city_selection else cities_all, 
        key="city_filter",
        placeholder="All cities selected" if len(st.session_state.get("city_selection", cities_all)) == len(cities_all) else "Choose cities..."
    )
    
    # Update session state
    st.session_state.city_selection = city_filter if city_filter else cities_all
    
    # Display summary below the multiselect
    if len(city_filter) == len(cities_all):
        st.info("📍 **All Cities** selected")
    elif len(city_filter) == 0:
        st.warning("⚠️ No cities selected")
    else:
        st.success(f"📍 **{len(city_filter)}** of **{len(cities_all)}** cities selected")

with col_f2:
    if city_filter:
        communities_filtered = df_wide[df_wide["City"].isin(city_filter)]["Community"].dropna().unique()
    else:
        communities_filtered = []

    communities_filtered = sorted(list(communities_filtered))

    # --- Fix: Ensure default values are VALID ---
    saved_selection = st.session_state.get("community_selection", communities_filtered)
    valid_selection = [c for c in saved_selection if c in communities_filtered]

    if not valid_selection:
        valid_selection = communities_filtered  # fallback: select all

    # --- Multiselect (safe) ---
    community_filter = st.multiselect(
        "Select Community",
        options=communities_filtered,
        default=valid_selection,
        key="community_filter",
        placeholder=(
            "All communities selected"
            if len(valid_selection) == len(communities_filtered)
            else "Choose communities..."
        ),
    )

    # Update session state safely
    st.session_state.community_selection = community_filter if community_filter else communities_filtered

    # Display summary below
    if len(community_filter) == len(communities_filtered):
        st.info("🏘️ **All Communities** selected")
    elif len(community_filter) == 0:
        st.warning("⚠️ No communities selected")
    else:
        st.success(f"🏘️ **{len(community_filter)}** of **{len(communities_filtered)}** communities selected")

with col_f3:
    month_filter = st.selectbox("Select Month", options=months, index=len(months)-1, key="month_filter")

# Apply filters (use all if none selected)
actual_city_filter = city_filter if city_filter else cities_all
actual_community_filter = community_filter if community_filter else list(communities_filtered)

df_filtered = df_wide[
    (df_wide["City"].isin(actual_city_filter)) &
    (df_wide["Community"].isin(actual_community_filter))
].copy()

# ---------------- Summary KPIs ----------------
st.markdown("---")
st.markdown("### 📊 Key Performance Indicators")

# Get the selected month's metrics
metric_cols_for_month = [c for c in df_filtered.columns if c.endswith(month_filter)]
tonnage_col = next((c for c in metric_cols_for_month if c.startswith("Tonnage_")), None)
trees_col = next((c for c in metric_cols_for_month if c.startswith("Trees_Saved_")), None)
co2_col = next((c for c in metric_cols_for_month if c.startswith("CO2_Kgs_Averted_")), None)
participation_col = next((c for c in metric_cols_for_month if c.startswith("Households_Participation_Percent_")), None)
compliance_col = next((c for c in metric_cols_for_month if c.startswith("Segregation_Compliance_Percent_")), None)

kpi_c1, kpi_c2, kpi_c3, kpi_c4, kpi_c5 = st.columns(5)

with kpi_c1:
    if tonnage_col:
        total_tonnage = df_filtered[tonnage_col].sum()
        st.metric("Total Tonnage", f"{total_tonnage:,.0f} kg")
    else:
        st.metric("Total Tonnage", "N/A")

with kpi_c2:
    if trees_col:
        total_trees = df_filtered[trees_col].sum()
        st.metric("Trees Saved", f"{total_trees:,.0f}")
    else:
        st.metric("Trees Saved", "N/A")

with kpi_c3:
    if co2_col:
        total_co2 = df_filtered[co2_col].sum()
        st.metric("CO₂ Averted", f"{total_co2:,.0f} kg")
    else:
        st.metric("CO₂ Averted", "N/A")

with kpi_c4:
    if participation_col:
        avg_participation = df_filtered[participation_col].mean()
        st.metric("Avg Participation", f"{avg_participation:.1f}%")
    else:
        st.metric("Avg Participation", "N/A")

with kpi_c5:
    if compliance_col:
        avg_compliance = df_filtered[compliance_col].mean()
        st.metric("Avg Compliance", f"{avg_compliance:.1f}%")
    else:
        st.metric("Avg Compliance", "N/A")

st.markdown("---")

# ---------------- Map Visualization ----------------
st.markdown(f"### 🗺️ Interactive Map ({map_type})")

# Prepare map data
map_df = df_filtered.dropna(subset=["Latitude", "Longitude"]).copy()

if map_df.empty:
    st.warning("⚠️ No location data available for selected filters.")
else:
    if map_type == "2D Map (Folium)":
        # ---------------- 2D FOLIUM MAP ----------------
        center_lat = map_df["Latitude"].mean()
        center_lon = map_df["Longitude"].mean()
        
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=11,
            tiles="OpenStreetMap",
            control_scale=True
        )
        
        # Add heatmap layer if selected
        if heatmap_metric != "None":
            # Map metric name to column name
            metric_mapping = {
                "Tonnage": tonnage_col,
                "Trees Saved": trees_col,
                "CO2 Kgs Averted": co2_col,
                "Households Participation %": participation_col,
                "Segregation Compliance %": compliance_col
            }
            
            heatmap_col = metric_mapping.get(heatmap_metric)
            if heatmap_col and heatmap_col in map_df.columns:
                heat_data = []
                for idx, row in map_df.iterrows():
                    if pd.notna(row[heatmap_col]) and row[heatmap_col] > 0:
                        # Normalize the weight
                        weight = row[heatmap_col] / map_df[heatmap_col].max()
                        heat_data.append([row["Latitude"], row["Longitude"], weight])
                
                if heat_data:
                    HeatMap(
                        heat_data,
                        min_opacity=0.2,
                        max_opacity=0.8,
                        radius=15,
                        blur=20,
                        gradient={0.2: 'blue', 0.4: 'lime', 0.6: 'yellow', 0.8: 'orange', 1.0: 'red'}
                    ).add_to(m)
        
        # Add markers
        marker_cluster = MarkerCluster().add_to(m)
        
        for idx, row in map_df.iterrows():
            # Build popup content
            # STEP 1 — Generate donut BEFORE popup_html
            tonnage_donut = tonnage_monthly_donut_base64(
                df_long,
                city=row["City"],
                community=row["Community"]
            )

            # STEP 2 & 3 — REPLACE the popup builder completely with function call
            popup_html = build_community_popup_html(
                row=row,
                tonnage_col=tonnage_col,
                trees_col=trees_col,
                co2_col=co2_col,
                participation_col=participation_col,
                compliance_col=compliance_col,
                community_id=row.get("community_id", ""),
                TREE_ICON=TREE_ICON,
                HOUSE_ICON=HOUSE_ICON
            )
            popup_html += f"""
            <hr>
            <div style="text-align:center;">
                <div style="font-weight:600; color:{BRAND_PRIMARY}; margin-bottom:6px;">
                    Monthly Tonnage Distribution
                </div>
                {tonnage_donut}
            </div>
            """

            popup_html += "</div>"
            
            folium.Marker(
                location=[row["Latitude"], row["Longitude"]],
                popup=folium.Popup(folium.IFrame(html=popup_html, width=560, height=340), max_width=560),
                tooltip=row["Community"],
                icon=folium.Icon(color="purple", icon="recycle", prefix="fa")
            ).add_to(marker_cluster)
        
        # Display map
        st_folium(m, width=None, height=ST_MAP_HEIGHT, returned_objects=ST_RETURNED_OBJECTS)
    
    else:
    # ---------------- 3D PYDECK MAP (CLEAN VERSION) ----------------
    
    # ---------------- 3D PYDECK MAP (WHITE BACKGROUND) ----------------
        st.markdown("#### 🧭 3D Extruded View")

        # Map metric name → column name
        metric_mapping = {
            "Tonnage": tonnage_col,
            "Trees Saved": trees_col,
            "CO2 Kgs Averted": co2_col,
            "Households Participation %": participation_col,
            "Segregation Compliance %": compliance_col
        }
        extrude_col = metric_mapping.get(extrude_metric)

        if extrude_col is None or extrude_col not in map_df.columns:
            st.warning("⚠️ Selected metric not available for 3D extrusion.")
        else:
            # Normalize height for extrusion
            df_3d = map_df.copy()
            max_val = df_3d[extrude_col].max()
            df_3d["height"] = (
                df_3d[extrude_col] / max_val * 800
                if max_val > 0 else 50
            )

            layer = pdk.Layer(
                "ColumnLayer",
                data=df_3d,
                get_position=["Longitude", "Latitude"],
                get_elevation="height",
                elevation_scale=1,
                radius=120,
                get_fill_color="[180, 140, 255, 180]",  # soft purple
                pickable=True,
                auto_highlight=True,
                extruded=True
            )

            view_state = pdk.ViewState(
                latitude=df_3d["Latitude"].mean(),
                longitude=df_3d["Longitude"].mean(),
                zoom=11,
                pitch=55,
                bearing=20
            )

            deck = pdk.Deck(
                layers=[layer],
                initial_view_state=view_state,
                tooltip={
                    "html": """
                    <b>Community:</b> {Community}<br/>
                    <b>City:</b> {City}<br/>
                    <b>Value:</b> {""" + extrude_col + """}
                    """,
                    "style": {
                        "backgroundColor": "white",
                        "color": "black"
                    }
                },
                map_style="light"  # ✅ white background
            )

            st.pydeck_chart(deck, use_container_width=True)

            st.markdown("---")

    # ---------------- Charts Section ----------------
    st.markdown("### 📈 Analytics & Trends")

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.markdown("#### Tonnage Trend Over Time")
        tonnage_trend = df_long[
            (df_long["City"].isin(actual_city_filter)) &
            (df_long["Community"].isin(actual_community_filter)) &
            (df_long["Metric"] == "Tonnage")
        ].groupby("Date")["Value"].sum().reset_index()
        
        if not tonnage_trend.empty:
            fig_tonnage = px.line(
                tonnage_trend,
                x="Date",
                y="Value",
                title="Total Tonnage Over Time",
                labels={"Value": "Tonnage (kg)", "Date": "Month"},
                markers=True
            )
            fig_tonnage.update_traces(line_color=BRAND_PRIMARY)
            st.plotly_chart(fig_tonnage, use_container_width=True)
        else:
            st.info("No tonnage data available")

    with chart_col2:
        st.markdown("#### Participation Rate Trend")
        participation_trend = df_long[
            (df_long["City"].isin(actual_city_filter)) &
            (df_long["Community"].isin(actual_community_filter)) &
            (df_long["Metric"] == "Households_Participation_Percent")
        ].groupby("Date")["Value"].mean().reset_index()
        
        if not participation_trend.empty:
            fig_participation = px.line(
                participation_trend,
                x="Date",
                y="Value",
                title="Average Participation Rate Over Time",
                labels={"Value": "Participation (%)", "Date": "Month"},
                markers=True
            )
            fig_participation.update_traces(line_color="green")
            st.plotly_chart(fig_participation, use_container_width=True)
        else:
            st.info("No participation data available")

    st.markdown("---")

    # ---------------- COMMUNITY/CITY ANALYSIS REPORT SECTION ----------------
    st.markdown("### 📊 Generate Analysis Report")
    st.markdown("Generate a comprehensive analysis report for a specific community or city with detailed trends and insights.")

    report_col1, report_col2 = st.columns([2, 1])

    with report_col1:
        report_type = st.radio(
            "Report Type",
            options=["Community Report", "City Report"],
            horizontal=True,
            key="report_type"
        )
        
        if report_type == "Community Report":
            # Select city first, then community
            report_city = st.selectbox(
                "Select City",
                options=sorted(df_wide["City"].unique()),
                key="report_city"
            )
            
            communities_in_city = df_wide[df_wide["City"] == report_city]["Community"].unique()
            report_community = st.selectbox(
                "Select Community",
                options=sorted(communities_in_city),
                key="report_community"
            )
            
            report_entity_name = f"{report_community}, {report_city}"
            report_filter = (df_long["Community"] == report_community) & (df_long["City"] == report_city)
            
        else:  # City Report
            report_city = st.selectbox(
                "Select City",
                options=sorted(df_wide["City"].unique()),
                key="report_city_only"
            )
            
            report_entity_name = report_city
            report_filter = df_long["City"] == report_city

    with report_col2:
        st.markdown("#### Report Options")
        include_all_metrics = st.checkbox("Include all metrics", value=True, key="include_all")
        
        if st.button("📄 Generate Report", type="primary", use_container_width=True):
            st.session_state.generate_report = True

    # Generate and display report
    if st.session_state.get("generate_report", False):
        st.markdown("---")
        st.markdown(f"## 📑 Analysis Report: {report_entity_name}")
        st.caption(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Filter data for the selected entity
        report_data = df_long[report_filter].copy()
        
        if report_data.empty:
            st.warning(f"⚠️ No data available for {report_entity_name}")
        else:
            # Summary statistics
            st.markdown("### 📌 Summary Statistics")
            
            summary_metrics = {}
            for metric in ["Tonnage", "Trees_Saved", "CO2_Kgs_Averted", "Households_Participation_Percent", "Segregation_Compliance_Percent"]:
                metric_data = report_data[report_data["Metric"] == metric]["Value"]
                if not metric_data.empty:
                    summary_metrics[metric] = {
                        "Total": metric_data.sum() if metric in ["Tonnage", "Trees_Saved", "CO2_Kgs_Averted"] else None,
                        "Average": metric_data.mean(),
                        "Max": metric_data.max(),
                        "Min": metric_data.min(),
                        "Latest": metric_data.iloc[-1]
                    }
            
            # Display summary in columns
            sum_cols = st.columns(5)
            metric_labels = {
                "Tonnage": "Total Tonnage",
                "Trees_Saved": "Trees Saved",
                "CO2_Kgs_Averted": "CO₂ Averted",
                "Households_Participation_Percent": "Avg Participation",
                "Segregation_Compliance_Percent": "Avg Compliance"
            }
            
            for idx, (metric, label) in enumerate(metric_labels.items()):
                if metric in summary_metrics:
                    with sum_cols[idx]:
                        if summary_metrics[metric]["Total"] is not None:
                            st.metric(label, f"{summary_metrics[metric]['Total']:,.0f}")
                        else:
                            st.metric(label, f"{summary_metrics[metric]['Average']:.1f}%")
            
            st.markdown("---")
            
            # Detailed trend charts
            st.markdown("### 📈 Detailed Trend Analysis")
            
            metrics_to_plot = [
                ("Tonnage", "Tonnage (kg)", BRAND_PRIMARY),
                ("Trees_Saved", "Trees Saved", "green"),
                ("CO2_Kgs_Averted", "CO₂ Averted (kg)", "orange"),
                ("Households_Participation_Percent", "Participation (%)", "blue"),
                ("Segregation_Compliance_Percent", "Compliance (%)", "red")
            ]
            
            for metric, label, color in metrics_to_plot:
                metric_trend = report_data[report_data["Metric"] == metric].sort_values("Date")
                
                if not metric_trend.empty:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=metric_trend["Date"],
                        y=metric_trend["Value"],
                        mode='lines+markers',
                        name=label,
                        line=dict(color=color, width=3),
                        marker=dict(size=8)
                    ))
                    
                    fig.update_layout(
                        title=f"{label} Trend",
                        xaxis_title="Date",
                        yaxis_title=label,
                        hovermode='x unified',
                        height=400
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("---")
            
            # Data table
            st.markdown("### 📋 Raw Data")
            
            # Pivot the data for better display
            pivot_data = report_data.pivot_table(
                index="Date",
                columns="Metric",
                values="Value",
                aggfunc="sum"
            ).reset_index()
            
            pivot_data.columns.name = None
            pivot_data["Date"] = pivot_data["Date"].dt.strftime("%Y-%m")
            
            st.dataframe(pivot_data, use_container_width=True, height=400)
            
            # Download button for report data
            csv_report = pivot_data.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Report Data as CSV",
                data=csv_report,
                file_name=f"analysis_report_{report_entity_name.replace(', ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )

    st.markdown("---")

# ---------------- Data Table ----------------
st.markdown("### 📋 Detailed Data Table")

# Show selected month's data
display_cols = ["City", "Community", "Pincode"]
if tonnage_col:
    display_cols.append(tonnage_col)
if trees_col:
    display_cols.append(trees_col)
if co2_col:
    display_cols.append(co2_col)
if participation_col:
    display_cols.append(participation_col)
if compliance_col:
    display_cols.append(compliance_col)

display_df = df_filtered[display_cols].copy()

# Rename columns for better display
rename_map = {}
if tonnage_col:
    rename_map[tonnage_col] = "Tonnage (kg)"
if trees_col:
    rename_map[trees_col] = "Trees Saved"
if co2_col:
    rename_map[co2_col] = "CO₂ Averted (kg)"
if participation_col:
    rename_map[participation_col] = "Participation (%)"
if compliance_col:
    rename_map[compliance_col] = "Compliance (%)"

display_df = display_df.rename(columns=rename_map)

st.dataframe(display_df, use_container_width=True, height=400)

# Download button
csv_data = display_df.to_csv(index=False).encode('utf-8')
st.download_button(
    label="📥 Download Filtered Data as CSV",
    data=csv_data,
    file_name=f"bintix_data_{month_filter}.csv",
    mime="text/csv"
)

st.markdown("---")
st.markdown(
    "<p style='text-align: center; color: gray;'>Built with ❤️ by Bintix Analytics Team</p>",
    unsafe_allow_html=True
)
