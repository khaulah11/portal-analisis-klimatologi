import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os
import calendar
import io
import re
import zipfile
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ============================================================
# 1. KONFIGURASI HALAMAN
# ============================================================
st.set_page_config(
    page_title="Rainfall & Climatology Analysis",
    page_icon="🌧️",
    layout="wide"
)

st.title("🌧️ Rainfall Data Analysis & Climatology System")
st.caption("Pemprosesan Berkelajuan Tinggi, Kawalan Kualiti Automatik, dan Analisis Lanjutan Siri Masa Hujan")

# ============================================================
# 2. TETAPAN BAR SISI (SIDEBAR)
# ============================================================
st.sidebar.header("⚙️ Analysis Settings")

LANG = st.sidebar.selectbox("🌐 Bahasa / Language", ["Bahasa Melayu", "English"])

START_YEAR = st.sidebar.number_input("Start Year", min_value=1900, max_value=2100, value=2016, step=1)
END_YEAR = st.sidebar.number_input("End Year", min_value=1900, max_value=2100, value=2025, step=1)

if START_YEAR > END_YEAR:
    st.sidebar.error("Start Year mesti lebih kecil atau sama dengan End Year.")
    st.stop()

years = list(range(int(START_YEAR), int(END_YEAR) + 1))
YEAR_RANGE_TEXT = f"{int(START_YEAR)}–{int(END_YEAR)}"

target_year = int(st.sidebar.number_input("Target Year", min_value=1900, max_value=2100, value=2018, step=1))

st.sidebar.subheader("WMO Missing Data Rule")
MAX_MISSING_DAYS = int(st.sidebar.number_input("Maximum missing days", min_value=0, max_value=31, value=10, step=1))
MAX_CONSECUTIVE_MISSING = int(st.sidebar.number_input("Maximum consecutive missing days", min_value=1, max_value=31, value=4, step=1))

st.sidebar.subheader("🌧️ Rainfall Threshold")
VALID_MIN = 0.0
WET_DAY_MIN = float(st.sidebar.number_input("Wet day threshold (mm)", min_value=0.0, value=0.1, step=0.01))
SUSPECT_RAINFALL = float(st.sidebar.number_input("Suspect threshold (mm)", min_value=0.0, value=150.0, step=10.0))
EXTREME_RAINFALL = float(st.sidebar.number_input("Extreme threshold (mm)", min_value=0.0, value=250.0, step=10.0))

months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ============================================================
# 3. TETAPAN GRAF & PALET WARNA
# ============================================================
RAINFALL_MIN = 0
RAINFALL_MAX = 500

st.sidebar.header("🎨 Plot Settings")
BG_COLOR = st.sidebar.color_picker("Background Graf", "#FFFFFF")

default_colors = ["#4682B4", "#87CEEB", "#3CB371", "#32CD32", "#FFD700", "#FFA500", "#FF7F50", "#FF6347", "#9370DB", "#DA70D6", "#6A5ACD", "#008080"]

if "bar_colors" not in st.session_state:
    st.session_state.bar_colors = default_colors.copy()
if "max_daily_color" not in st.session_state:
    st.session_state.max_daily_color = "#FF6347"
if "wet_days_color" not in st.session_state:
    st.session_state.wet_days_color = "#3CB371"
if "std_color" not in st.session_state:
    st.session_state.std_color = "#9370DB"
if "hist_color" not in st.session_state:
    st.session_state.hist_color = "#4682B4"

selected_chart = st.sidebar.selectbox("Select Bar Chart", ["Monthly Rainfall", "Maximum Daily Rainfall", "Wet Days", "Standard Deviation", "Histogram"])

if selected_chart == "Monthly Rainfall":
    selected_month = st.sidebar.selectbox("Select Month", months)
    selected_index = months.index(selected_month)
    st.session_state.bar_colors[selected_index] = st.sidebar.color_picker(f"{selected_month} Bar Colour", st.session_state.bar_colors[selected_index])
elif selected_chart == "Maximum Daily Rainfall":
    st.session_state.max_daily_color = st.sidebar.color_picker("Maximum Daily Rainfall Colour", st.session_state.max_daily_color)
elif selected_chart == "Wet Days":
    st.session_state.wet_days_color = st.sidebar.color_picker("Wet Days Colour", st.session_state.wet_days_color)
elif selected_chart == "Standard Deviation":
    st.session_state.std_color = st.sidebar.color_picker("Standard Deviation Colour", st.session_state.std_color)
elif selected_chart == "Histogram":
    st.session_state.hist_color = st.sidebar.color_picker("Histogram Colour", st.session_state.hist_color)

LINE_COLOR = st.sidebar.color_picker("Mean Line", "#000000")
MIN_COLOR = st.sidebar.color_picker("Minimum", "#008000")
MAX_COLOR = st.sidebar.color_picker("Maximum", "#FF0000")
FIG_WIDTH, FIG_HEIGHT = 14, 8

# ============================================================
# 4. ENJIN VEKTORISASI & CACHING BERKELAJUAN TINGGI
# ============================================================

def normalize_station_name(val):
    val = str(val).replace(":", "").strip()
    val = re.sub(r'[<>:"/\\|?*]', '', val)
    return re.sub(r'\s+', ' ', val).strip().upper() if val else "UNKNOWN_STATION"

def max_consecutive_missing_vectorized(series):
    """Pengiraan pantas turutan missing tanpa iterasi manual"""
    if series.empty or not series.isna().any():
        return 0
    is_na = series.isna().astype(int)
    blocks = (is_na != is_na.shift()).cumsum()
    consec = is_na.groupby(blocks).transform('sum') * is_na
    max_val = consec.max()
    return int(max_val) if pd.notna(max_val) else 0

def parse_sheet_raw(raw_df, sheet_name):
    """Mengekstrak data siri masa 4 lajur mentah"""
    start_row = 11
    for r in range(min(15, len(raw_df))):
        row_txt = " ".join([str(x).lower() for x in raw_df.iloc[r].tolist() if pd.notna(x)])
        if ("year" in row_txt or "tahun" in row_txt) and ("month" in row_txt or "bulan" in row_txt):
            start_row = r + 1
            break

    st_name = ""
    for r in range(min(8, len(raw_df))):
        for c in range(min(6, len(raw_df.columns))):
            cell_str = str(raw_df.iloc[r, c]).strip()
            if any(k in cell_str.lower() for k in ['station', 'stesen', 'stn']):
                if ':' in cell_str and len(cell_str.split(':', 1)[1].strip()) > 1:
                    st_name = cell_str.split(':', 1)[1].strip()
                elif c + 1 < len(raw_df.columns) and pd.notna(raw_df.iloc[r, c + 1]):
                    st_name = str(raw_df.iloc[r, c + 1]).strip()
    if not st_name:
        st_name = str(sheet_name).strip()
    st_name = normalize_station_name(st_name)

    data = raw_df.iloc[start_row:].copy().iloc[:, :4]
    data.columns = ["Year", "Month", "Day", "Rainfall"]
    data["Rainfall"] = data["Rainfall"].astype(str).str.strip().str.upper().replace(['TR', 'TRACE'], '0.1')
    
    data["Year"] = pd.to_numeric(data["Year"], errors="coerce")
    data["Month"] = pd.to_numeric(data["Month"], errors="coerce")
    data["Day"] = pd.to_numeric(data["Day"], errors="coerce")
    data["Rainfall"] = pd.to_numeric(data["Rainfall"], errors="coerce")

    data = data.dropna(subset=["Year", "Month", "Day"])
    data = data[data["Year"].between(1900, 2100)]
    data["Year"] = data["Year"].astype(int)
    data["Month"] = data["Month"].astype(int)
    data["Day"] = data["Day"].astype(int)
    return st_name, data

def parse_sheet_matrix(file_bytes, year, is_xls):
    """Membaca format matriks 31x12 bertab tahun"""
    engine = "xlrd" if is_xls else "openpyxl"
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=str(year), header=6, engine=engine)
    if df is None or df.empty or df.shape[1] < 13:
        return None
    df = df.iloc[:, :13].copy()
    df.columns = ["hari"] + months
    df["hari"] = pd.to_numeric(df["hari"], errors="coerce")
    df = df[df["hari"].between(1, 31)].copy()

    melted = df.melt(id_vars=["hari"], value_vars=months, var_name="Month_Str", value_name="Rainfall")
    m_map = {m: i+1 for i, m in enumerate(months)}
    melted["Month"] = melted["Month_Str"].map(m_map)
    melted["Day"] = melted["hari"].astype(int)
    melted["Year"] = int(year)
    melted["Rainfall"] = pd.to_numeric(melted["Rainfall"], errors="coerce")
    return melted[["Year", "Month", "Day", "Rainfall"]]

@st.cache_data(show_spinner=False)
def process_and_analyze_all(files_payload, years_tuple, tgt_yr, max_miss, max_consec, v_min, wet_min, susp_th, extr_th):
    """Enjin teras berpusat: Mengimbas, membersihkan, dan menganalisis semua fail serentak secara cache"""
    station_raw_store = {}
    
    for filename, file_bytes in files_payload:
        is_xls = filename.lower().endswith(".xls")
        excel = pd.ExcelFile(io.BytesIO(file_bytes))
        sheet_names = excel.sheet_names
        year_sheets = [s for s in sheet_names if str(s).strip().isdigit() and int(str(s).strip()) in years_tuple]

        if len(year_sheets) > 0:
            st_name = normalize_station_name(os.path.splitext(filename)[0])
            if st_name not in station_raw_store:
                station_raw_store[st_name] = []
            for yr in years_tuple:
                df_yr = parse_sheet_matrix(file_bytes, yr, is_xls)
                if df_yr is not None:
                    station_raw_store[st_name].append(df_yr)
        else:
            for s_name in sheet_names:
                if str(s_name).lower().strip() in ['datalist', 'info', 'summary', 'sheet1']:
                    continue
                raw_df = pd.read_excel(excel, sheet_name=s_name, header=None)
                st_name, df_clean = parse_sheet_raw(raw_df, s_name)
                if df_clean is not None and not df_clean.empty:
                    if st_name not in station_raw_store:
                        station_raw_store[st_name] = []
                    station_raw_store[st_name].append(df_clean)

    station_results = {}
    
    for st_name, df_list in station_raw_store.items():
        if not df_list:
            continue
        data_df = pd.concat(df_list, ignore_index=True).drop_duplicates(subset=["Year", "Month", "Day"], keep="first")
        data_df.loc[data_df["Rainfall"] < v_min, "Rainfall"] = np.nan

        # Vektorisasi Rekod Suspect & Ekstrem
        suspect_df = data_df[data_df["Rainfall"] > susp_th][["Year", "Month", "Day", "Rainfall"]].copy()
        suspect_df["Status"] = "SUSPECT - SEMAK"
        extreme_df = data_df[data_df["Rainfall"] > extr_th][["Year", "Month", "Day", "Rainfall"]].copy()
        extreme_df["Status"] = "EXTREME - DOUBLE CHECK"

        # Vektorisasi Matriks Harian & Pengiraan Tahunan
        avail_years = sorted(data_df["Year"].unique())
        daily_dfs = []
        for yr in avail_years:
            df_yr = data_df[data_df["Year"] == yr]
            pivot = df_yr.pivot(index="Day", columns="Month", values="Rainfall").reindex(index=range(1, 32), columns=range(1, 13))
            pivot.columns = months
            pivot.insert(0, "hari", pivot.index)
            pivot["Year"] = int(yr)
            daily_dfs.append(pivot)
            
        all_daily = pd.concat(daily_dfs, ignore_index=True) if daily_dfs else pd.DataFrame()

        yearly_monthly_total = pd.DataFrame(index=avail_years, columns=months, dtype=float)
        monthly_missing_count = pd.DataFrame(index=avail_years, columns=months, dtype=float)
        monthly_valid_count = pd.DataFrame(index=avail_years, columns=months, dtype=float)
        monthly_max_consec = pd.DataFrame(index=avail_years, columns=months, dtype=float)
        monthly_qc_status = pd.DataFrame(index=avail_years, columns=months, dtype=object)

        for yr in avail_years:
            yr_df = data_df[data_df["Year"] == yr]
            for m_num, m_name in enumerate(months, start=1):
                days_exp = calendar.monthrange(int(yr), m_num)[1]
                vals = yr_df[yr_df["Month"] == m_num]["Rainfall"]
                
                v_cnt = vals.notna().sum()
                m_cnt = days_exp - v_cnt
                c_cnt = max_consecutive_missing_vectorized(vals)

                monthly_valid_count.loc[yr, m_name] = v_cnt
                monthly_missing_count.loc[yr, m_name] = m_cnt
                monthly_max_consec.loc[yr, m_name] = c_cnt

                if m_cnt <= max_miss and c_cnt <= max_consec:
                    yearly_monthly_total.loc[yr, m_name] = vals.sum(skipna=True)
                    monthly_qc_status.loc[yr, m_name] = "ACCEPT"
                else:
                    yearly_monthly_total.loc[yr, m_name] = np.nan
                    monthly_qc_status.loc[yr, m_name] = "REJECT"

        curr_tgt_yr = tgt_yr if tgt_yr in avail_years else (avail_years[-1] if avail_years else tgt_yr)
        rainfall_target = yearly_monthly_total.loc[curr_tgt_yr].reindex(months) if curr_tgt_yr in yearly_monthly_total.index else pd.Series(np.nan, index=months)
        mean_monthly_total = yearly_monthly_total.mean(axis=0, skipna=True).reindex(months)

        anomaly_percent = ((rainfall_target - mean_monthly_total) / mean_monthly_total) * 100
        anomaly_percent[mean_monthly_total == 0] = np.nan

        # Statistik Ringkasan Tahun Sasaran
        tgt_data = data_df[data_df["Year"] == curr_tgt_yr]
        median_d, std_d, max_d, min_d, wet_d, valid_pct = [], [], [], [], [], []

        for m_num, m_name in enumerate(months, start=1):
            days_exp = calendar.monthrange(curr_tgt_yr, m_num)[1] if curr_tgt_yr else 31
            m_vals = tgt_data[tgt_data["Month"] == m_num]["Rainfall"].dropna()
            w_vals = m_vals[m_vals >= wet_min]

            valid_pct.append((len(m_vals) / days_exp) * 100 if days_exp else 0)
            median_d.append(w_vals.median() if len(w_vals) > 0 else np.nan)
            std_d.append(w_vals.std() if len(w_vals) > 1 else np.nan)
            max_d.append(w_vals.max() if len(w_vals) > 0 else np.nan)
            min_d.append(w_vals.min() if len(w_vals) > 0 else np.nan)
            wet_d.append(len(w_vals))

        analysis_table = pd.DataFrame({
            "Month": months,
            f"Total {curr_tgt_yr} (mm)": rainfall_target.values,
            f"Mean {YEAR_RANGE_TEXT} (mm)": mean_monthly_total.values,
            f"Anomaly {curr_tgt_yr} (%)": anomaly_percent.values,
            "Median Daily (>=0.1 mm)": median_d,
            "SD Daily (>=0.1 mm)": std_d,
            "Maximum Daily (>=0.1 mm)": max_d,
            "Minimum Daily (>=0.1 mm)": min_d,
            "Wet Days (>=0.1 mm)": wet_d,
            "Valid Data (%)": valid_pct
        })

        # Kategori Hujan Vektorisasi
        pie_vals = tgt_data["Rainfall"].dropna().values
        cat_vals = [
            int((pie_vals == 0.0).sum()),
            int(((pie_vals >= 0.1) & (pie_vals <= 2.5)).sum()),
            int(((pie_vals > 2.5) & (pie_vals <= 10.0)).sum()),
            int(((pie_vals > 10.0) & (pie_vals <= 50.0)).sum()),
            int((pie_vals > 50.0).sum())
        ]

        station_results[st_name] = {
            "all_daily": all_daily,
            "data_df": data_df,
            "yearly_monthly_total": yearly_monthly_total,
            "rainfall_target": rainfall_target,
            "mean_monthly_total": mean_monthly_total,
            "anomaly_percent": anomaly_percent,
            "min_target_month": rainfall_target.idxmin() if rainfall_target.notna().any() else None,
            "min_target_value": rainfall_target.min() if rainfall_target.notna().any() else None,
            "max_target_month": rainfall_target.idxmax() if rainfall_target.notna().any() else None,
            "max_target_value": rainfall_target.max() if rainfall_target.notna().any() else None,
            "min_mean_month": mean_monthly_total.idxmin() if mean_monthly_total.notna().any() else None,
            "min_mean_value": mean_monthly_total.min() if mean_monthly_total.notna().any() else None,
            "max_mean_month": mean_monthly_total.idxmax() if mean_monthly_total.notna().any() else None,
            "max_mean_value": mean_monthly_total.max() if mean_monthly_total.notna().any() else None,
            "max_daily": max_d, "wet_days": wet_d, "std_daily": std_d,
            "hist_values": pie_vals[pie_vals >= wet_min],
            "category_values": cat_vals,
            "category_labels": ["No Rain (0.0 mm)", "Light Rain (0.1–2.5 mm)", "Moderate Rain (>2.5–10.0 mm)", "Heavy Rain (>10.0-50.0 mm)", "Extreme Rain (>50 mm)"],
            "analysis_table": analysis_table,
            "suspect_df": suspect_df,
            "extreme_df": extreme_df,
            "target_year": curr_tgt_yr
        }

    return station_results

# ============================================================
# 5. RUANG MUAT NAIK & PEMPROSESAN DATA
# ============================================================

uploaded_files = st.file_uploader(
    "📁 Upload Excel file data hujan AAWS (Fail Mentah atau Fail Terformat):",
    type=["xlsx", "xls"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.info("👈 Sila muat naik fail Excel untuk memulakan analisis.")
    st.stop()

# Sediakan payload fail (tuple nama & bytes) untuk keserasian cache Streamlit
files_payload = tuple((f.name, f.getvalue()) for f in uploaded_files)

with st.spinner("⚡ Memproses data dengan enjin pantas..."):
    station_results = process_and_analyze_all(
        files_payload,
        tuple(years),
        target_year,
        MAX_MISSING_DAYS,
        MAX_CONSECUTIVE_MISSING,
        VALID_MIN,
        WET_DAY_MIN,
        SUSPECT_RAINFALL,
        EXTREME_RAINFALL
    )

if not station_results:
    st.error("⚠️ Tiada data sah berjaya dikesan daripada fail yang dimuat naik.")
    st.stop()

# ============================================================
# 6. PENGEPALA & KAWALAN PAPARAN BERPUSAT
# ============================================================
st.divider()

col_nav1, col_nav2 = st.columns([3, 1])
with col_nav1:
    selected_station = st.selectbox(
        "📍 **Pilih Stesen untuk Dianalisis:**",
        options=sorted(list(station_results.keys()))
    )
with col_nav2:
    st.write("")
    st.success(f"✅ **{len(station_results)} Stesen Unik** Sedia Digunakan")

current_res = station_results[selected_station]
curr_tgt_yr = current_res["target_year"]

# Metrik KPI Pantas
kpi_c1, kpi_c2, kpi_c3, kpi_c4, kpi_c5 = st.columns(5)
kpi_c1.metric(f"Min {curr_tgt_yr}", f"{current_res['min_target_value']:.1f} mm" if current_res['min_target_value'] is not None else "N.A.", current_res['min_target_month'])
kpi_c2.metric(f"Maks {curr_tgt_yr}", f"{current_res['max_target_value']:.1f} mm" if current_res['max_target_value'] is not None else "N.A.", current_res['max_target_month'])
kpi_c3.metric("Purata Min", f"{current_res['min_mean_value']:.1f} mm" if current_res['min_mean_value'] is not None else "N.A.", current_res['min_mean_month'])
kpi_c4.metric("Purata Maks", f"{current_res['max_mean_value']:.1f} mm" if current_res['max_mean_value'] is not None else "N.A.", current_res['max_mean_month'])
kpi_c5.metric("Rekod QC Suspect", f"{len(current_res['suspect_df'])} Rekod")

st.markdown("---")

# ============================================================
# 7. RUANG KERJA ANALISIS & VISUALISASI BERSEPADU
# ============================================================

main_tabs = st.tabs([
    "📊 Graf Analisis Lengkap (11 Tab)",
    "🌐 Pandangan Awam (Public)",
    "🔬 Analisis Trend Saintifik",
    "📈 Perbandingan Merentas Stesen",
    "📋 Jadual Statistik & Muat Turun"
])

# ------------------------------------------------------------
# TAB 1: 11 GRAF LENGKAP ASAL (SUB-TABS KEMAS)
# ------------------------------------------------------------
with main_tabs[0]:
    st.subheader(f"📊 Visualisasi Saintifik Terperinci — {selected_station}")
    
    sub_plot_tabs = st.tabs([
        "📊 Bar + Line", "🔥 Heatmap", "📉 Anomaly",
        "📈 Max Daily", "🌧️ Wet Days", "📐 Std Dev",
        "📊 Histogram", "🥧 Kategori Hujan", "📦 Boxplot"
    ])
    
    x = np.arange(len(months))
    
    # 1. Bar + Line
    with sub_plot_tabs[0]:
        fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        ax.bar(x, current_res["rainfall_target"].values, width=0.60, color=st.session_state.bar_colors, edgecolor="black", linewidth=0.8, label=f"Total Rainfall {curr_tgt_yr}")
        ax.plot(x, current_res["mean_monthly_total"].values, color=LINE_COLOR, marker="o", linewidth=2.5, markersize=7, label=f"Mean Monthly Rainfall {YEAR_RANGE_TEXT}")
        for i, value in enumerate(current_res["mean_monthly_total"].values):
            if pd.notna(value):
                ax.annotate(f"{value:.1f}", (i, value), xytext=(0, 10), textcoords="offset points", ha="center", fontsize=10, fontweight="bold")
        ax.set_title(f"{selected_station}\nMonthly Rainfall {curr_tgt_yr} vs Mean Monthly Rainfall {YEAR_RANGE_TEXT}", fontsize=14, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(months)
        ax.set_ylabel("Rainfall (mm)")
        ax.grid(True, axis="y", linestyle="--", alpha=0.4)
        ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9)
        plt.tight_layout()
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)

    # 2. Heatmap
    with sub_plot_tabs[1]:
        plot_data = current_res["yearly_monthly_total"].reindex(columns=months)
        fig, ax = plt.subplots(figsize=(14, 7))
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        valid_vals = plot_data.values[~pd.isna(plot_data.values)]
        vmin, vmax = (valid_vals.min(), valid_vals.max()) if len(valid_vals) > 0 else (0, 1)
        if vmin == vmax: vmax = vmin + 1
        im = ax.imshow(plot_data.values, aspect="auto", cmap="YlGnBu", vmin=vmin, vmax=vmax)
        ax.set_xticks(range(len(months)))
        ax.set_xticklabels(months)
        ax.set_yticks(range(len(plot_data.index)))
        ax.set_yticklabels(plot_data.index.astype(str))
        for i in range(len(plot_data.index)):
            for j in range(len(months)):
                val = plot_data.iloc[i, j]
                ax.text(j, i, f"{val:.0f}" if pd.notna(val) else "N.A.", ha="center", va="center", fontsize=7)
        fig.colorbar(im, ax=ax).set_label("Total Rainfall (mm)")
        ax.set_title(f"{selected_station}\nMonthly Total Rainfall Heatmap ({YEAR_RANGE_TEXT})", fontsize=14, fontweight="bold")
        plt.tight_layout()
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)

    # 3. Anomaly
    with sub_plot_tabs[2]:
        fig, ax = plt.subplots(figsize=(14, 7))
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        anom_colors = ["lightgray" if pd.isna(v) else ("darkorange" if v >= 0 else "steelblue") for v in current_res["anomaly_percent"].values]
        bars = ax.bar(x, current_res["anomaly_percent"].values, width=0.60, color=anom_colors, edgecolor="black", linewidth=0.8)
        ax.axhline(0, color="black", linewidth=1)
        for bar, val in zip(bars, current_res["anomaly_percent"].values):
            if pd.notna(val):
                offset, vertical = (4, "bottom") if val >= 0 else (-12, "top")
                ax.annotate(f"{val:.1f}%", (bar.get_x() + bar.get_width() / 2, val), xytext=(0, offset), textcoords="offset points", ha="center", va=vertical, fontsize=8)
        ax.set_title(f"{selected_station}\nRainfall Anomaly {curr_tgt_yr} vs Mean ({YEAR_RANGE_TEXT})", fontsize=14, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(months)
        ax.set_ylabel("Anomaly (%)")
        ax.grid(True, axis="y", linestyle="--", alpha=0.4)
        plt.tight_layout()
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)

    # 4. Max Daily
    with sub_plot_tabs[3]:
        fig, ax = plt.subplots(figsize=(14, 7))
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        bars = ax.bar(x, current_res["max_daily"], width=0.60, color=st.session_state.max_daily_color, edgecolor="black", linewidth=0.8)
        for bar, val in zip(bars, current_res["max_daily"]):
            if pd.notna(val): ax.annotate(f"{val:.1f}", (bar.get_x() + bar.get_width()/2, val), xytext=(0, 6), textcoords="offset points", ha="center", fontsize=9, fontweight="bold")
        ax.set_title(f"{selected_station}\nMaximum Daily Rainfall - {curr_tgt_yr}", fontsize=14, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(months)
        ax.grid(True, axis="y", linestyle="--", alpha=0.4)
        plt.tight_layout()
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)

    # 5. Wet Days
    with sub_plot_tabs[4]:
        fig, ax = plt.subplots(figsize=(14, 7))
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        bars = ax.bar(x, current_res["wet_days"], width=0.60, color=st.session_state.wet_days_color, edgecolor="black", linewidth=0.8)
        for bar, val in zip(bars, current_res["wet_days"]):
            if pd.notna(val): ax.annotate(f"{int(val)}", (bar.get_x() + bar.get_width()/2, val), xytext=(0, 6), textcoords="offset points", ha="center", fontsize=9, fontweight="bold")
        ax.set_title(f"{selected_station}\nNumber of Wet Days (≥0.1 mm) - {curr_tgt_yr}", fontsize=14, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(months)
        ax.grid(True, axis="y", linestyle="--", alpha=0.4)
        plt.tight_layout()
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)

    # 6. Standard Deviation
    with sub_plot_tabs[5]:
        fig, ax = plt.subplots(figsize=(14, 7))
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        bars = ax.bar(x, current_res["std_daily"], width=0.60, color=st.session_state.std_color, edgecolor="black", linewidth=0.8)
        for bar, val in zip(bars, current_res["std_daily"]):
            if pd.notna(val): ax.annotate(f"{val:.1f}", (bar.get_x() + bar.get_width()/2, val), xytext=(0, 6), textcoords="offset points", ha="center", fontsize=9, fontweight="bold")
        ax.set_title(f"{selected_station}\nDaily Rainfall Standard Deviation - {curr_tgt_yr}", fontsize=14, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(months)
        ax.grid(True, axis="y", linestyle="--", alpha=0.4)
        plt.tight_layout()
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)

    # 7. Histogram
    with sub_plot_tabs[6]:
        if len(current_res["hist_values"]) > 0:
            fig, ax = plt.subplots(figsize=(14, 7))
            fig.patch.set_facecolor(BG_COLOR)
            ax.set_facecolor(BG_COLOR)
            ax.hist(current_res["hist_values"], bins=15, color=st.session_state.hist_color, edgecolor="black", linewidth=0.8)
            ax.set_title(f"{selected_station}\nDistribution of Daily Rainfall - {curr_tgt_yr}", fontsize=14, fontweight="bold")
            ax.set_xlabel("Daily Rainfall (mm)")
            ax.set_ylabel("Number of Days")
            ax.grid(True, axis="y", linestyle="--", alpha=0.4)
            plt.tight_layout()
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
        else:
            st.warning("Tiada data hujan ≥ 0.1 mm untuk histogram.")

    # 8. Rainfall Category
    with sub_plot_tabs[7]:
        if sum(current_res["category_values"]) > 0:
            fig, ax = plt.subplots(figsize=(9, 7))
            fig.patch.set_facecolor(BG_COLOR)
            ax.set_facecolor(BG_COLOR)
            ax.pie(current_res["category_values"], labels=current_res["category_labels"], autopct="%1.1f%%", startangle=90, counterclock=False, wedgeprops={"edgecolor":"black", "linewidth":0.8})
            ax.set_title(f"{selected_station}\nPercentage of Days by Category - {curr_tgt_yr}", fontsize=14, fontweight="bold")
            plt.tight_layout()
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
        else:
            st.warning("Tiada data sah untuk pie chart.")

    # 9. Boxplot
    with sub_plot_tabs[8]:
        target_df = current_res["data_df"][current_res["data_df"]["Year"] == curr_tgt_yr]
        b_data, b_labels = [], []
        for m_num, m_name in enumerate(months, start=1):
            vals = target_df[target_df["Month"] == m_num]["Rainfall"].dropna()
            w_vals = vals[vals >= WET_DAY_MIN].tolist()
            b_data.append(w_vals)
            b_labels.append(m_name)
            
        if any(len(v) > 0 for v in b_data):
            fig, ax = plt.subplots(figsize=(14, 7))
            fig.patch.set_facecolor(BG_COLOR)
            ax.set_facecolor(BG_COLOR)
            bp = ax.boxplot(b_data, tick_labels=b_labels, patch_artist=True, showmeans=True, meanline=False, showfliers=True)
            for box in bp["boxes"]: box.set(facecolor="#87CEEB", edgecolor="black", linewidth=1)
            for median in bp["medians"]: median.set(color="red", linewidth=2)
            for mean in bp["means"]: mean.set(marker="o", markerfacecolor="black", markeredgecolor="black", markersize=5)
            ax.set_title(f"{selected_station}\nDaily Rainfall Distribution by Month - {curr_tgt_yr}", fontsize=14, fontweight="bold")
            ax.grid(True, axis="y", linestyle="--", alpha=0.4)
            plt.tight_layout()
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
        else:
            st.warning("Tiada data mencukupi untuk boxplot.")

# ------------------------------------------------------------
# TAB 2: PANDANGAN AWAM (PUBLIC DASHBOARD)
# ------------------------------------------------------------
with main_tabs[1]:
    st.subheader(f"🌐 Ringkasan Iklim Awam — {selected_station}")
    valid_means = current_res["mean_monthly_total"].dropna()
    if len(valid_means) > 0:
        c_p1, c_p2, c_p3 = st.columns(3)
        c_p1.metric("Purata Hujan Tahunan", f"{valid_means.sum():.1f} mm")
        c_p2.metric("Bulan Paling Basah", f"{valid_means.idxmax()} ({valid_means.max():.1f} mm)")
        c_p3.metric("Bulan Paling Kering", f"{valid_means.idxmin()} ({valid_means.min():.1f} mm)")

        cp_left, cp_right = st.columns([6, 4])
        with cp_left:
            fig_pub = px.bar(x=months, y=current_res["mean_monthly_total"].values, text=current_res["mean_monthly_total"].values, labels={'x':'Bulan', 'y':'Purata Hujan (mm)'}, title="Purata Penerimaan Hujan Bulanan Normal")
            fig_pub.update_traces(texttemplate='%{text:.1f} mm', textposition='outside')
            st.plotly_chart(fig_pub, use_container_width=True)
        with cp_right:
            tot_days = sum(current_res["category_values"])
            rain_days = tot_days - current_res["category_values"][0]
            donut_df = pd.DataFrame({'Kategori': ['Hari Berhujan (≥0.1mm)', 'Hari Kering (0.0mm)'], 'Jumlah': [rain_days, current_res["category_values"][0]]})
            st.plotly_chart(px.pie(donut_df, names='Kategori', values='Jumlah', hole=0.5, color_discrete_sequence=['#1f77b4', '#ffa500']), use_container_width=True)

# ------------------------------------------------------------
# TAB 3: ANALISIS TREND SAINTIFIK
# ------------------------------------------------------------
with main_tabs[2]:
    st.subheader(f"🔬 Analisis Trend Jangka Panjang — {selected_station}")
    ann_totals = current_res["yearly_monthly_total"].sum(axis=1, min_count=10).dropna().reset_index()
    ann_totals.columns = ['Year', 'Rainfall']
    if len(ann_totals) > 1:
        z = np.polyfit(ann_totals['Year'], ann_totals['Rainfall'], 1)
        p = np.poly1d(z)
        ann_totals['Trend Line (y=mx+c)'] = p(ann_totals['Year'])
        fig_trend = px.line(
            ann_totals, x='Year', y=['Rainfall', 'Trend Line (y=mx+c)'],
            markers=True,
            title=f"Trend Hujan Tahunan dengan Kecerunan Regresi (m = {z[0]:.2f} mm/tahun)",
            labels={'value': 'Jumlah Hujan (mm)', 'Year': 'Tahun', 'variable': 'Petunjuk'},
            color_discrete_map={'Rainfall': '#1f77b4', 'Trend Line (y=mx+c)': '#ff7f0e'}
        )
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("Data tahunan tidak mencukupi untuk regresi linear.")

# ------------------------------------------------------------
# TAB 4: PERBANDINGAN MERENTAS STESEN
# ------------------------------------------------------------
with main_tabs[3]:
    st.subheader("📈 Perbandingan Merentas Berbilang Stesen (Multi-Station)")
    all_st_names = sorted(list(station_results.keys()))
    selected_compare = st.multiselect(
        "Pilih stesen-stesen untuk dibandingkan:",
        options=all_st_names,
        default=all_st_names[:min(4, len(all_st_names))]
    )
    
    if len(selected_compare) >= 2:
        comp_fig = go.Figure()
        for s_name in selected_compare:
            s_data = station_results[s_name]["mean_monthly_total"]
            comp_fig.add_trace(go.Scatter(
                x=months,
                y=s_data.values,
                mode='lines+markers',
                name=s_name
            ))
        comp_fig.update_layout(
            title=f"Perbandingan Purata Hujan Bulanan ({YEAR_RANGE_TEXT})",
            xaxis_title="Bulan",
            yaxis_title="Purata Hujan (mm)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(comp_fig, use_container_width=True)
    else:
        st.info("💡 Sila pilih sekurang-kurangnya 2 stesen di atas untuk menjana graf perbandingan bertindih.")

# ------------------------------------------------------------
# TAB 5: STATISTIK & MUAT TURUN
# ------------------------------------------------------------
with main_tabs[4]:
    st.subheader(f"📋 Jadual Statistik & Kawalan Kualiti — {selected_station}")
    st.dataframe(current_res["analysis_table"], use_container_width=True)
    
    st.download_button(
        "📥 Download Statistical Analysis CSV",
        current_res["analysis_table"].to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{selected_station}_Statistical_Analysis_{YEAR_RANGE_TEXT}.csv",
        mime="text/csv"
    )

# ============================================================
# 8. DOWNLOAD PUKAL (.ZIP)
# ============================================================

st.divider()
zip_buffer = io.BytesIO()
with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
    for st_name, res in station_results.items():
        zip_file.writestr(f"{st_name}/{st_name}_Statistical_Analysis_{YEAR_RANGE_TEXT}.csv", res["analysis_table"].to_csv(index=False))
        zip_file.writestr(f"{st_name}/{st_name}_Monthly_Total_{YEAR_RANGE_TEXT}.csv", res["yearly_monthly_total"].to_csv())
        zip_file.writestr(f"{st_name}/{st_name}_Suspect_Rainfall.csv", res["suspect_df"].to_csv(index=False))

zip_buffer.seek(0)
st.download_button(
    label="📦 Muat Turun Semua Keputusan Stesen (ZIP)",
    data=zip_buffer.getvalue(),
    file_name=f"Rainfall_Analysis_All_Stations_{YEAR_RANGE_TEXT}.zip",
    mime="application/zip",
    type="primary"
)

st.caption("© 2026 Jabatan Meteorologi Malaysia (MetMalaysia) | Pejabat Meteorologi Sabah.")