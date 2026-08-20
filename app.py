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
# 1. KONFIGURASI HALAMAN & TEMA
# ============================================================
st.set_page_config(
    page_title="Sistem Analisis Klimatologi AAWS | MetMalaysia Sabah",
    page_icon="🌤️",
    layout="wide"
)

# Custom Styling untuk kekemasan UI
st.markdown("""
    <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
        div[data-testid="stMetricValue"] { font-size: 1.35rem; font-weight: 700; }
        .stTabs [data-baseweb="tab-list"] { gap: 12px; }
        .stTabs [data-baseweb="tab"] {
            border-radius: 6px 6px 0px 0px;
            padding: 8px 16px;
            font-weight: 600;
        }
    </style>
""", unsafe_allow_html=True)

# Header Utama
h_col1, h_col2 = st.columns([1, 8])
with h_col1:
    st.markdown("<h1 style='font-size: 40px; margin: 0;'>🌤️</h1>", unsafe_allow_html=True)
with h_col2:
    st.markdown("### **Sistem Integrasi Analisis & Klimatologi AAWS**")
    st.caption("Jabatan Meteorologi Malaysia (MetMalaysia) | Pejabat Meteorologi Sabah | WMO-No. 1203 Logic")

st.divider()

# ============================================================
# 2. TETAPAN BAR SISI (SIDEBAR)
# ============================================================
st.sidebar.header("⚙️ Tetapan Analisis")

START_YEAR = st.sidebar.number_input("Start Year", min_value=1900, max_value=2100, value=2016, step=1)
END_YEAR = st.sidebar.number_input("End Year", min_value=1900, max_value=2100, value=2025, step=1)

if START_YEAR > END_YEAR:
    st.sidebar.error("Start Year mesti <= End Year.")
    st.stop()

years = list(range(int(START_YEAR), int(END_YEAR) + 1))
YEAR_RANGE_TEXT = f"{int(START_YEAR)}–{int(END_YEAR)}"
target_year = int(st.sidebar.number_input("Target Year", min_value=1900, max_value=2100, value=2018, step=1))

st.sidebar.markdown("---")
st.sidebar.subheader("🛡️ Piawaian Data & QC WMO")
MAX_MISSING_DAYS = int(st.sidebar.number_input("Maks. Hari Hilang (Sebulan)", min_value=0, max_value=31, value=10, step=1))
MAX_CONSECUTIVE_MISSING = int(st.sidebar.number_input("Maks. Berturut-turut Hilang", min_value=1, max_value=31, value=4, step=1))
WET_DAY_MIN = float(st.sidebar.number_input("Had Hari Berhujan (mm)", min_value=0.0, value=0.1, step=0.01))
SUSPECT_RAINFALL = float(st.sidebar.number_input("Had Suspect (mm)", min_value=0.0, value=150.0, step=10.0))
EXTREME_RAINFALL = float(st.sidebar.number_input("Had Ekstrem (mm)", min_value=0.0, value=250.0, step=10.0))

months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Pilihan Warna Bar Sisi (Kekal Seperti Asal)
st.sidebar.markdown("---")
st.sidebar.header("🎨 Tetapan Warna Graf")
BG_COLOR = st.sidebar.color_picker("Latar Belakang Graf", "#FFFFFF")

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

selected_chart_color = st.sidebar.selectbox("Pilih Graf untuk Ubah Warna", ["Monthly Rainfall", "Maximum Daily Rainfall", "Wet Days", "Standard Deviation", "Histogram"])

if selected_chart_color == "Monthly Rainfall":
    sel_m = st.sidebar.selectbox("Pilih Bulan", months)
    sel_idx = months.index(sel_m)
    st.session_state.bar_colors[sel_idx] = st.sidebar.color_picker(f"Warna {sel_m}", st.session_state.bar_colors[sel_idx])
elif selected_chart_color == "Maximum Daily Rainfall":
    st.session_state.max_daily_color = st.sidebar.color_picker("Warna Max Daily", st.session_state.max_daily_color)
elif selected_chart_color == "Wet Days":
    st.session_state.wet_days_color = st.sidebar.color_picker("Warna Wet Days", st.session_state.wet_days_color)
elif selected_chart_color == "Standard Deviation":
    st.session_state.std_color = st.sidebar.color_picker("Warna Standard Deviation", st.session_state.std_color)
elif selected_chart_color == "Histogram":
    st.session_state.hist_color = st.sidebar.color_picker("Warna Histogram", st.session_state.hist_color)

LINE_COLOR = st.sidebar.color_picker("Warna Garis Purata (Mean)", "#000000")
MIN_COLOR = st.sidebar.color_picker("Warna Titik Minimum", "#008000")
MAX_COLOR = st.sidebar.color_picker("Warna Titik Maksimum", "#FF0000")

# ============================================================
# 3. ENJIN PENGECAMAN & CACHING PANTAS
# ============================================================
def normalize_station_name(val):
    val = str(val).replace(":", "").strip()
    val = re.sub(r'[<>:"/\\|?*]', '', val)
    return re.sub(r'\s+', ' ', val).strip().upper() if val else "UNKNOWN_STATION"

def max_consecutive_missing_vectorized(series):
    if series.empty or not series.isna().any():
        return 0
    is_na = series.isna().astype(int)
    blocks = (is_na != is_na.shift()).cumsum()
    consec = is_na.groupby(blocks).transform('sum') * is_na
    max_val = consec.max()
    return int(max_val) if pd.notna(max_val) else 0

def parse_sheet_raw(raw_df, sheet_name):
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
    data["Rainfall"] = data["Rainfall"].astype(str).str.strip().str.upper().replace(['TR', 'TRACE'], '0.1')[cite: 2]
    
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
    engine = "xlrd" if is_xls else "openpyxl"
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=str(year), header=6, engine=engine)[cite: 3]
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
def process_all_files(files_payload, years_tuple, tgt_yr, max_miss, max_consec, wet_min, susp_th, extr_th):
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
        data_df.loc[data_df["Rainfall"] < 0, "Rainfall"] = np.nan

        suspect_df = data_df[data_df["Rainfall"] > susp_th][["Year", "Month", "Day", "Rainfall"]].copy()[cite: 3]
        suspect_df["Status"] = "SUSPECT - SEMAK"[cite: 3]
        extreme_df = data_df[data_df["Rainfall"] > extr_th][["Year", "Month", "Day", "Rainfall"]].copy()[cite: 3]
        extreme_df["Status"] = "EXTREME - DOUBLE CHECK"[cite: 3]

        avail_years = sorted(data_df["Year"].unique())
        yearly_monthly_total = pd.DataFrame(index=avail_years, columns=months, dtype=float)
        monthly_missing_count = pd.DataFrame(index=avail_years, columns=months, dtype=float)[cite: 3]
        monthly_valid_count = pd.DataFrame(index=avail_years, columns=months, dtype=float)[cite: 3]
        monthly_max_consec = pd.DataFrame(index=avail_years, columns=months, dtype=float)
        monthly_qc_status = pd.DataFrame(index=avail_years, columns=months, dtype=object)

        for yr in avail_years:
            yr_df = data_df[data_df["Year"] == yr]
            for m_num, m_name in enumerate(months, start=1):
                days_exp = calendar.monthrange(int(yr), m_num)[1][cite: 3]
                vals = yr_df[yr_df["Month"] == m_num]["Rainfall"]
                v_cnt = vals.notna().sum()
                m_cnt = days_exp - v_cnt
                c_cnt = max_consecutive_missing_vectorized(vals)

                monthly_valid_count.loc[yr, m_name] = v_cnt
                monthly_missing_count.loc[yr, m_name] = m_cnt
                monthly_max_consec.loc[yr, m_name] = c_cnt

                if m_cnt <= max_miss and c_cnt <= max_consec:
                    yearly_monthly_total.loc[yr, m_name] = vals.sum(skipna=True)
                    monthly_qc_status.loc[yr, m_name] = "ACCEPT"[cite: 3]
                else:
                    yearly_monthly_total.loc[yr, m_name] = np.nan[cite: 3]
                    monthly_qc_status.loc[yr, m_name] = "REJECT"[cite: 3]

        curr_tgt_yr = tgt_yr if tgt_yr in avail_years else (avail_years[-1] if avail_years else tgt_yr)
        rainfall_target = yearly_monthly_total.loc[curr_tgt_yr].reindex(months) if curr_tgt_yr in yearly_monthly_total.index else pd.Series(np.nan, index=months)
        mean_monthly_total = yearly_monthly_total.mean(axis=0, skipna=True).reindex(months)[cite: 3]

        anomaly_percent = ((rainfall_target - mean_monthly_total) / mean_monthly_total) * 100[cite: 3]
        anomaly_percent[mean_monthly_total == 0] = np.nan[cite: 3]

        tgt_data = data_df[data_df["Year"] == curr_tgt_yr]
        median_d, std_d, max_d, min_d, wet_d, valid_pct = [], [], [], [], [], []

        for m_num, m_name in enumerate(months, start=1):
            days_exp = calendar.monthrange(curr_tgt_yr, m_num)[1] if curr_tgt_yr else 31[cite: 3]
            m_vals = tgt_data[tgt_data["Month"] == m_num]["Rainfall"].dropna()
            w_vals = m_vals[m_vals >= wet_min]

            valid_pct.append((len(m_vals) / days_exp) * 100 if days_exp else 0)
            median_d.append(w_vals.median() if len(w_vals) > 0 else np.nan)[cite: 3]
            std_d.append(w_vals.std() if len(w_vals) > 1 else np.nan)[cite: 3]
            max_d.append(w_vals.max() if len(w_vals) > 0 else np.nan)[cite: 3]
            min_d.append(w_vals.min() if len(w_vals) > 0 else np.nan)[cite: 3]
            wet_d.append(len(w_vals))

        analysis_table = pd.DataFrame({
            "Month": months,[cite: 3]
            f"Total {curr_tgt_yr} (mm)": rainfall_target.values,[cite: 3]
            f"Mean {YEAR_RANGE_TEXT} (mm)": mean_monthly_total.values,[cite: 3]
            f"Anomaly {curr_tgt_yr} (%)": anomaly_percent.values,[cite: 3]
            "Median Daily (>=0.1 mm)": median_d,[cite: 3]
            "SD Daily (>=0.1 mm)": std_d,[cite: 3]
            "Maximum Daily (>=0.1 mm)": max_d,[cite: 3]
            "Minimum Daily (>=0.1 mm)": min_d,[cite: 3]
            "Wet Days (>=0.1 mm)": wet_d,[cite: 3]
            "Valid Data (%)": valid_pct
        })

        pie_vals = tgt_data["Rainfall"].dropna().values
        cat_vals = [
            int((pie_vals == 0.0).sum()),[cite: 3]
            int(((pie_vals >= 0.1) & (pie_vals <= 2.5)).sum()),[cite: 3]
            int(((pie_vals > 2.5) & (pie_vals <= 10.0)).sum()),[cite: 3]
            int(((pie_vals > 10.0) & (pie_vals <= 50.0)).sum()),[cite: 3]
            int((pie_vals > 50.0).sum())[cite: 3]
        ]

        station_results[st_name] = {
            "data_df": data_df,
            "yearly_monthly_total": yearly_monthly_total,
            "monthly_missing_count": monthly_missing_count,[cite: 3]
            "monthly_valid_count": monthly_valid_count,[cite: 3]
            "monthly_max_consec": monthly_max_consec,
            "monthly_qc_status": monthly_qc_status,
            "rainfall_target": rainfall_target,
            "mean_monthly_total": mean_monthly_total,
            "anomaly_percent": anomaly_percent,
            "min_target_month": rainfall_target.idxmin() if rainfall_target.notna().any() else None,[cite: 3]
            "min_target_value": rainfall_target.min() if rainfall_target.notna().any() else None,[cite: 3]
            "max_target_month": rainfall_target.idxmax() if rainfall_target.notna().any() else None,[cite: 3]
            "max_target_value": rainfall_target.max() if rainfall_target.notna().any() else None,[cite: 3]
            "min_mean_month": mean_monthly_total.idxmin() if mean_monthly_total.notna().any() else None,[cite: 3]
            "min_mean_value": mean_monthly_total.min() if mean_monthly_total.notna().any() else None,[cite: 3]
            "max_mean_month": mean_monthly_total.idxmax() if mean_monthly_total.notna().any() else None,[cite: 3]
            "max_mean_value": mean_monthly_total.max() if mean_monthly_total.notna().any() else None,[cite: 3]
            "max_daily": max_d,[cite: 3]
            "wet_days": wet_d,[cite: 3]
            "std_daily": std_d,[cite: 3]
            "hist_values": pie_vals[pie_vals >= wet_min],
            "category_values": cat_vals,
            "category_labels": ["No Rain (0.0 mm)", "Light Rain (0.1–2.5 mm)", "Moderate Rain (>2.5–10.0 mm)", "Heavy Rain (>10.0-50.0 mm)", "Extreme Rain (>50 mm)"],[cite: 3]
            "analysis_table": analysis_table,
            "suspect_df": suspect_df,
            "extreme_df": extreme_df,
            "target_year": curr_tgt_yr
        }

    return station_results

# ============================================================
# 4. RUANG MUAT NAIK & SELEKSI STESEN
# ============================================================
uploaded_files = st.file_uploader("📁 Muat naik fail AAWS (.xls / .xlsx):", type=["xlsx", "xls"], accept_multiple_files=True)

if not uploaded_files:
    st.info("👈 Sila muat naik fail data AAWS di atas untuk memulakan analisis.")
    st.stop()

files_payload = tuple((f.name, f.getvalue()) for f in uploaded_files)

with st.spinner("⚡ Memproses data siri masa..."):
    station_results = process_all_files(files_payload, tuple(years), target_year, MAX_MISSING_DAYS, MAX_CONSECUTIVE_MISSING, WET_DAY_MIN, SUSPECT_RAINFALL, EXTREME_RAINFALL)

if not station_results:
    st.error("⚠️ Tiada data sah dijumpai.")
    st.stop()

# Bar Pemilihan Stesen
c_sel, c_stat = st.columns([3.5, 1.5])
with c_sel:
    selected_station = st.selectbox("📍 **Pilih Stesen Cerapan:**", options=sorted(list(station_results.keys())))
with c_stat:
    st.write("")
    st.success(f"**{len(station_results)} Stesen** Sedia Dianalisis")

st_data = station_results[selected_station]
curr_tgt_yr = st_data["target_year"]
valid_means = st_data["mean_monthly_total"].dropna()

# Kad KPI Ringkasan Eksekutif
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Purata Hujan Tahunan", f"{valid_means.sum():.1f} mm" if not valid_means.empty else "N.A.")
k2.metric("Bulan Kemuncak", f"{valid_means.idxmax()} ({valid_means.max():.1f} mm)" if not valid_means.empty else "N.A.")
k3.metric("Bulan Terkering", f"{valid_means.idxmin()} ({valid_means.min():.1f} mm)" if not valid_means.empty else "N.A.")
k4.metric(f"Total Hujan ({curr_tgt_yr})", f"{st_data['rainfall_target'].sum():.1f} mm" if st_data['rainfall_target'].notna().any() else "N.A.")
k5.metric("Rekod QC (Suspect/Ekstrem)", f"{len(st_data['suspect_df']) + len(st_data['extreme_df'])} Hari")

st.markdown("---")

# ============================================================
# 5. RUANG NAVIGASI UTAMA (3 TAB BERSIH & TERATUR)
# ============================================================
tab_visual, tab_multi, tab_data = st.tabs([
    "📊 Galeri Analisis & Visualisasi Lengkap",
    "📈 Perbandingan Merentas Stesen",
    "📋 Jadual Statistik & Arkib Laporan"
])

# ------------------------------------------------------------
# TAB 1: GALERI VISUALISASI (SEMUA 11 GRAF DENGAN DROPDOWN PINTAR)
# ------------------------------------------------------------
with tab_visual:
    v_col1, v_col2 = st.columns([3, 1])
    with v_col1:
        chosen_view = st.selectbox(
            "🎯 **Pilih Graf yang Ingin Dipaparkan:**",
            [
                "1. Bar + Line (Hujan Sasaran vs Purata Normal)",
                "2. Matriks Kalendar Harian (Heatmap 365 Hari)",
                "3. Anomali Iklim (Departure from Normal)",
                "4. Rekod Hujan Harian Maksimum (Max Daily)",
                "5. Bilangan Hari Berhujan (Wet Days)",
                "6. Sisihan Piawai Harian (Standard Deviation)",
                "7. Histogram Taburan Hujan Harian",
                "8. Carta Pai Kategori Hujan (MetMalaysia)",
                "9. Boxplot Taburan Hujan Bulanan (IQR & Outlier)",
                "10. Trend Jangka Panjang & Garis Regresi Linear",
                "11. Nisbah Hari Berhujan vs Hari Kering (Donut Chart)"
            ]
        )
    with v_col2:
        st.write("")
        st.caption(f"Tahun Sasaran: **{curr_tgt_yr}** | Normal: **{YEAR_RANGE_TEXT}**")

    x = np.arange(len(months))

    # 1. Bar + Line
    if chosen_view.startswith("1."):
        fig, ax = plt.subplots(figsize=(14, 7))
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        ax.bar(x, st_data["rainfall_target"].values, width=0.60, color=st.session_state.bar_colors, edgecolor="black", linewidth=0.8, label=f"Total Rainfall {curr_tgt_yr}")[cite: 3]
        ax.plot(x, st_data["mean_monthly_total"].values, color=LINE_COLOR, marker="o", linewidth=2.5, markersize=7, label=f"Mean Monthly Rainfall {YEAR_RANGE_TEXT}")[cite: 3]
        for i, val in enumerate(st_data["mean_monthly_total"].values):
            if pd.notna(val): ax.annotate(f"{val:.1f}", (i, val), xytext=(0, 10), textcoords="offset points", ha="center", fontsize=10, fontweight="bold")[cite: 3]
        ax.set_title(f"{selected_station} — Monthly Rainfall {curr_tgt_yr} vs Mean Normal ({YEAR_RANGE_TEXT})", fontsize=14, fontweight="bold")[cite: 3]
        ax.set_xticks(x); ax.set_xticklabels(months); ax.set_ylabel("Rainfall (mm)")[cite: 3]
        ax.grid(True, axis="y", linestyle="--", alpha=0.4); ax.legend(loc="upper left")[cite: 3]
        plt.tight_layout(); st.pyplot(fig, use_container_width=True); plt.close(fig)[cite: 3]

    # 2. Heatmap
    elif chosen_view.startswith("2."):
        plot_data = st_data["yearly_monthly_total"].reindex(columns=months)[cite: 3]
        fig, ax = plt.subplots(figsize=(14, 7))
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        valid_vals = plot_data.values[~pd.isna(plot_data.values)][cite: 3]
        vmin, vmax = (valid_vals.min(), valid_vals.max()) if len(valid_vals) > 0 else (0, 1)[cite: 3]
        im = ax.imshow(plot_data.values, aspect="auto", cmap="YlGnBu", vmin=vmin, vmax=vmax)[cite: 3]
        ax.set_xticks(range(len(months))); ax.set_xticklabels(months)[cite: 3]
        ax.set_yticks(range(len(plot_data.index))); ax.set_yticklabels(plot_data.index.astype(str))[cite: 3]
        for i in range(len(plot_data.index)):
            for j in range(len(months)):
                val = plot_data.iloc[i, j]
                ax.text(j, i, f"{val:.0f}" if pd.notna(val) else "N.A.", ha="center", va="center", fontsize=7)[cite: 3]
        fig.colorbar(im, ax=ax).set_label("Total Rainfall (mm)")[cite: 3]
        ax.set_title(f"{selected_station} — Matriks Hujan Bulanan ({YEAR_RANGE_TEXT})", fontsize=14, fontweight="bold")[cite: 3]
        plt.tight_layout(); st.pyplot(fig, use_container_width=True); plt.close(fig)[cite: 3]

    # 3. Anomaly
    elif chosen_view.startswith("3."):
        fig, ax = plt.subplots(figsize=(14, 7))
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        anom_colors = ["lightgray" if pd.isna(v) else ("darkorange" if v >= 0 else "steelblue") for v in st_data["anomaly_percent"].values][cite: 3]
        bars = ax.bar(x, st_data["anomaly_percent"].values, width=0.60, color=anom_colors, edgecolor="black", linewidth=0.8)[cite: 3]
        ax.axhline(0, color="black", linewidth=1)[cite: 3]
        for bar, val in zip(bars, st_data["anomaly_percent"].values):
            if pd.notna(val):
                offset, vertical = (4, "bottom") if val >= 0 else (-12, "top")[cite: 3]
                ax.annotate(f"{val:.1f}%", (bar.get_x() + bar.get_width() / 2, val), xytext=(0, offset), textcoords="offset points", ha="center", va=vertical, fontsize=8)[cite: 3]
        ax.set_title(f"{selected_station} — Anomali Hujan {curr_tgt_yr} Berbanding Purata Normal", fontsize=14, fontweight="bold")[cite: 3]
        ax.set_xticks(x); ax.set_xticklabels(months); ax.set_ylabel("Anomaly (%)")[cite: 3]
        ax.grid(True, axis="y", linestyle="--", alpha=0.4)[cite: 3]
        plt.tight_layout(); st.pyplot(fig, use_container_width=True); plt.close(fig)[cite: 3]

    # 4. Max Daily
    elif chosen_view.startswith("4."):
        fig, ax = plt.subplots(figsize=(14, 7))
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        bars = ax.bar(x, st_data["max_daily"], width=0.60, color=st.session_state.max_daily_color, edgecolor="black", linewidth=0.8)[cite: 3]
        for bar, val in zip(bars, st_data["max_daily"]):
            if pd.notna(val): ax.annotate(f"{val:.1f}", (bar.get_x() + bar.get_width()/2, val), xytext=(0, 6), textcoords="offset points", ha="center", fontsize=9, fontweight="bold")[cite: 3]
        ax.set_title(f"{selected_station} — Hujan Harian Maksimum ({curr_tgt_yr})", fontsize=14, fontweight="bold")[cite: 3]
        ax.set_xticks(x); ax.set_xticklabels(months); ax.grid(True, axis="y", linestyle="--", alpha=0.4)[cite: 3]
        plt.tight_layout(); st.pyplot(fig, use_container_width=True); plt.close(fig)[cite: 3]

    # 5. Wet Days
    elif chosen_view.startswith("5."):
        fig, ax = plt.subplots(figsize=(14, 7))
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        bars = ax.bar(x, st_data["wet_days"], width=0.60, color=st.session_state.wet_days_color, edgecolor="black", linewidth=0.8)[cite: 3]
        for bar, val in zip(bars, st_data["wet_days"]):
            if pd.notna(val): ax.annotate(f"{int(val)}", (bar.get_x() + bar.get_width()/2, val), xytext=(0, 6), textcoords="offset points", ha="center", fontsize=9, fontweight="bold")[cite: 3]
        ax.set_title(f"{selected_station} — Bilangan Hari Berhujan (≥0.1 mm) ({curr_tgt_yr})", fontsize=14, fontweight="bold")[cite: 3]
        ax.set_xticks(x); ax.set_xticklabels(months); ax.grid(True, axis="y", linestyle="--", alpha=0.4)[cite: 3]
        plt.tight_layout(); st.pyplot(fig, use_container_width=True); plt.close(fig)[cite: 3]

    # 6. Standard Deviation
    elif chosen_view.startswith("6."):
        fig, ax = plt.subplots(figsize=(14, 7))
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        bars = ax.bar(x, st_data["std_daily"], width=0.60, color=st.session_state.std_color, edgecolor="black", linewidth=0.8)[cite: 3]
        for bar, val in zip(bars, st_data["std_daily"]):
            if pd.notna(val): ax.annotate(f"{val:.1f}", (bar.get_x() + bar.get_width()/2, val), xytext=(0, 6), textcoords="offset points", ha="center", fontsize=9, fontweight="bold")[cite: 3]
        ax.set_title(f"{selected_station} — Sisihan Piawai Harian ({curr_tgt_yr})", fontsize=14, fontweight="bold")[cite: 3]
        ax.set_xticks(x); ax.set_xticklabels(months); ax.grid(True, axis="y", linestyle="--", alpha=0.4)[cite: 3]
        plt.tight_layout(); st.pyplot(fig, use_container_width=True); plt.close(fig)[cite: 3]

    # 7. Histogram
    elif chosen_view.startswith("7."):
        if len(st_data["hist_values"]) > 0:
            fig, ax = plt.subplots(figsize=(14, 7))
            fig.patch.set_facecolor(BG_COLOR)
            ax.set_facecolor(BG_COLOR)
            ax.hist(st_data["hist_values"], bins=15, color=st.session_state.hist_color, edgecolor="black", linewidth=0.8)[cite: 3]
            ax.set_title(f"{selected_station} — Taburan Kekerapan Hujan Harian ({curr_tgt_yr})", fontsize=14, fontweight="bold")[cite: 3]
            ax.set_xlabel("Hujan Harian (mm)"); ax.set_ylabel("Bilangan Hari")[cite: 3]
            ax.grid(True, axis="y", linestyle="--", alpha=0.4)[cite: 3]
            plt.tight_layout(); st.pyplot(fig, use_container_width=True); plt.close(fig)[cite: 3]
        else:
            st.warning("Tiada data hujan >= 0.1 mm untuk histogram.")[cite: 3]

    # 8. Kategori Hujan
    elif chosen_view.startswith("8."):
        if sum(st_data["category_values"]) > 0:
            fig, ax = plt.subplots(figsize=(9, 6.5))
            fig.patch.set_facecolor(BG_COLOR)
            ax.set_facecolor(BG_COLOR)
            ax.pie(st_data["category_values"], labels=st_data["category_labels"], autopct="%1.1f%%", startangle=90, counterclock=False, wedgeprops={"edgecolor":"black", "linewidth":0.8})[cite: 3]
            ax.set_title(f"{selected_station} — Peratusan Hari Mengikut Kategori ({curr_tgt_yr})", fontsize=14, fontweight="bold")[cite: 3]
            plt.tight_layout(); st.pyplot(fig, use_container_width=True); plt.close(fig)[cite: 3]

    # 9. Boxplot
    elif chosen_view.startswith("9."):
        tgt_df = st_data["data_df"][st_data["data_df"]["Year"] == curr_tgt_yr]
        b_data, b_labels = [], []
        for m_num, m_name in enumerate(months, start=1):
            vals = tgt_df[tgt_df["Month"] == m_num]["Rainfall"].dropna()
            b_data.append(vals[vals >= WET_DAY_MIN].tolist())
            b_labels.append(m_name)
            
        if any(len(v) > 0 for v in b_data):
            fig, ax = plt.subplots(figsize=(14, 7))
            fig.patch.set_facecolor(BG_COLOR)
            ax.set_facecolor(BG_COLOR)
            bp = ax.boxplot(b_data, tick_labels=b_labels, patch_artist=True, showmeans=True, meanline=False, showfliers=True)[cite: 3]
            for box in bp["boxes"]: box.set(facecolor="#87CEEB", edgecolor="black", linewidth=1)[cite: 3]
            for median in bp["medians"]: median.set(color="red", linewidth=2)[cite: 3]
            for mean in bp["means"]: mean.set(marker="o", markerfacecolor="black", markeredgecolor="black", markersize=5)[cite: 3]
            ax.set_title(f"{selected_station} — Taburan Hujan Bulanan (Boxplot) ({curr_tgt_yr})", fontsize=14, fontweight="bold")[cite: 3]
            ax.grid(True, axis="y", linestyle="--", alpha=0.4)[cite: 3]
            plt.tight_layout(); st.pyplot(fig, use_container_width=True); plt.close(fig)[cite: 3]

    # 10. Regresi Linear
    elif chosen_view.startswith("10."):
        ann_totals = st_data["yearly_monthly_total"].sum(axis=1, min_count=10).dropna().reset_index()[cite: 2]
        ann_totals.columns = ['Year', 'Rainfall'][cite: 2]
        if len(ann_totals) > 1:
            z = np.polyfit(ann_totals['Year'], ann_totals['Rainfall'], 1)[cite: 2]
            p = np.poly1d(z)[cite: 2]
            ann_totals['Trend Line'] = p(ann_totals['Year'])
            fig_tr = px.line(
                ann_totals, x='Year', y=['Rainfall', 'Trend Line'], markers=True,[cite: 2]
                title=f"{selected_station} — Trend Tahunan & Kecerunan Regresi (m = {z[0]:.2f} mm/tahun)",[cite: 2]
                color_discrete_map={'Rainfall': '#1f77b4', 'Trend Line': '#ff7f0e'}[cite: 2]
            )
            fig_tr.update_layout(height=420)
            st.plotly_chart(fig_tr, use_container_width=True)[cite: 2]

    # 11. Donut Chart
    elif chosen_view.startswith("11."):
        tot_days = sum(st_data["category_values"])
        rain_days = tot_days - st_data["category_values"][0]
        donut_df = pd.DataFrame({'Kategori': ['Hari Berhujan (≥0.1mm)', 'Hari Kering (0.0mm)'], 'Jumlah': [rain_days, st_data["category_values"][0]]})[cite: 2]
        fig_donut = px.pie(donut_df, names='Kategori', values='Jumlah', hole=0.55, title=f"{selected_station} — Nisbah Hari Berhujan ({curr_tgt_yr})", color_discrete_sequence=['#1f77b4', '#ffa500'])[cite: 2]
        fig_donut.update_layout(height=420)
        st.plotly_chart(fig_donut, use_container_width=True)[cite: 2]

# ------------------------------------------------------------
# TAB 2: PERBANDINGAN RENTAS STESEN
# ------------------------------------------------------------
with tab_multi:
    st.subheader("📈 Tindihan Profil Purata Bulanan Merentas Stesen")
    all_st_names = sorted(list(station_results.keys()))
    sel_compare = st.multiselect("Pilih 2 atau lebih stesen untuk dibandingkan:", all_st_names, default=all_st_names[:min(4, len(all_st_names))])
    
    if len(sel_compare) >= 2:
        comp_fig = go.Figure()
        for s in sel_compare:
            s_mean = station_results[s]["mean_monthly_total"]
            comp_fig.add_trace(go.Scatter(x=months, y=s_mean.values, mode='lines+markers', name=s))
        comp_fig.update_layout(title=f"Perbandingan Profil Hujan Bulanan ({YEAR_RANGE_TEXT})", height=450, xaxis_title="Bulan", yaxis_title="Hujan (mm)")
        st.plotly_chart(comp_fig, use_container_width=True)
    else:
        st.info("💡 Sila pilih sekurang-kurangnya 2 stesen di atas.")

# ------------------------------------------------------------
# TAB 3: JADUAL STATISTIK, QC & MUAT TURUN
# ------------------------------------------------------------
with tab_data:
    st.subheader(f"📋 Jadual Statistik Lengkap — {selected_station}")
    st.dataframe(st_data["analysis_table"], use_container_width=True)[cite: 3]
    
    st.markdown("#### 🛡️ Log Kawalan Kualiti Data (WMO)")
    q1, q2 = st.columns(2)
    with q1:
        st.write(f"Rekod Suspect (> {SUSPECT_RAINFALL:.0f} mm): **{len(st_data['suspect_df'])}**")[cite: 3]
        if not st_data['suspect_df'].empty:
            st.dataframe(st_data['suspect_df'], use_container_width=True, hide_index=True)[cite: 3]
    with q2:
        st.write(f"Rekod Ekstrem (> {EXTREME_RAINFALL:.0f} mm): **{len(st_data['extreme_df'])}**")[cite: 3]
        if not st_data['extreme_df'].empty:
            st.dataframe(st_data['extreme_df'], use_container_width=True, hide_index=True)[cite: 3]

    st.divider()
    d1, d2 = st.columns(2)
    with d1:
        st.download_button(
            "📥 Muat Turun CSV Stesen Ini",
            st_data["analysis_table"].to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{selected_station}_Analisis_{YEAR_RANGE_TEXT}.csv",
            mime="text/csv"
        )
    with d2:
        zip_buffer = io.BytesIO()[cite: 3]
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:[cite: 3]
            for s_name, res in station_results.items():
                zip_file.writestr(f"{s_name}/{s_name}_Statistical_Analysis.csv", res["analysis_table"].to_csv(index=False))[cite: 3]
                zip_file.writestr(f"{s_name}/{s_name}_Monthly_Totals.csv", res["yearly_monthly_total"].to_csv())[cite: 3]
        zip_buffer.seek(0)[cite: 3]
        st.download_button(
            "📦 Muat Turun Pakej ZIP Semua Stesen",
            data=zip_buffer.getvalue(),[cite: 3]
            file_name=f"Laporan_Klimatologi_Lengkap_{YEAR_RANGE_TEXT}.zip",[cite: 3]
            mime="application/zip",[cite: 3]
            type="primary"
        )

# ============================================================
# 6. FOOTER
# ============================================================
st.divider()
st.caption("© 2026 Jabatan Meteorologi Malaysia (MetMalaysia) | Pejabat Meteorologi Sabah.")