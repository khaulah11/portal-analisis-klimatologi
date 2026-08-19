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
# STREAMLIT CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Rainfall & Climatology Analysis",
    page_icon="🌧️",
    layout="wide"
)

st.title("🌧️ Rainfall Data Analysis & Climatology System")
st.caption("Pemprosesan Automatik Fail Mentah / Terformat, Quality Control, dan Analisis Lanjutan Siri Masa Hujan")

# ============================================================
# SIDEBAR SETTINGS
# ============================================================

st.sidebar.header("⚙️ Analysis Settings")

LANG = st.sidebar.selectbox("🌐 Bahasa / Language", ["Bahasa Melayu", "English"])

START_YEAR = st.sidebar.number_input(
    "Start Year",
    min_value=1900,
    max_value=2100,
    value=2016,
    step=1
)

END_YEAR = st.sidebar.number_input(
    "End Year",
    min_value=1900,
    max_value=2100,
    value=2025,
    step=1
)

if START_YEAR > END_YEAR:
    st.sidebar.error("Start Year mesti lebih kecil atau sama dengan End Year.")
    st.stop()

years = range(int(START_YEAR), int(END_YEAR) + 1)
YEAR_RANGE_TEXT = f"{int(START_YEAR)}–{int(END_YEAR)}"

target_year = st.sidebar.number_input(
    "Target Year",
    min_value=1900,
    max_value=2100,
    value=2018,
    step=1
)
target_year = int(target_year)

# ============================================================
# WMO MISSING DATA RULE
# ============================================================

st.sidebar.subheader("WMO Missing Data Rule")

MAX_MISSING_DAYS = st.sidebar.number_input(
    "Maximum missing days",
    min_value=0,
    max_value=31,
    value=10,
    step=1,
    help="Bulan ditolak jika bilangan missing days melebihi nilai ini. Default 10 bermaksud >=11 missing days ditolak."
)

MAX_CONSECUTIVE_MISSING = st.sidebar.number_input(
    "Maximum consecutive missing days",
    min_value=1,
    max_value=31,
    value=4,
    step=1,
    help="Bulan ditolak jika terdapat missing days berturut-turut melebihi nilai ini. Default 4 bermaksud >=5 berturut-turut ditolak."
)

# ============================================================
# RAINFALL THRESHOLDS
# ============================================================

st.sidebar.subheader("🌧️ Rainfall Threshold")

VALID_MIN = 0.0

WET_DAY_MIN = st.sidebar.number_input(
    "Wet day threshold (mm)",
    min_value=0.0,
    value=0.1,
    step=0.01
)

SUSPECT_RAINFALL = st.sidebar.number_input(
    "Suspect threshold (mm)",
    min_value=0.0,
    value=150.0,
    step=10.0
)

EXTREME_RAINFALL = st.sidebar.number_input(
    "Extreme threshold (mm)",
    min_value=0.0,
    value=250.0,
    step=10.0
)

months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]

# ============================================================
# GRAPH SETTINGS & PALETTE
# ============================================================

RAINFALL_MIN = 0
RAINFALL_MAX = 500

st.sidebar.header("🎨 Plot Settings")

BG_COLOR = st.sidebar.color_picker("Background Graf", "#FFFFFF")

default_colors = [
    "#4682B4", "#87CEEB", "#3CB371", "#32CD32",
    "#FFD700", "#FFA500", "#FF7F50", "#FF6347",
    "#9370DB", "#DA70D6", "#6A5ACD", "#008080"
]

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

chart_options = [
    "Monthly Rainfall",
    "Maximum Daily Rainfall",
    "Wet Days",
    "Standard Deviation",
    "Histogram"
]

selected_chart = st.sidebar.selectbox("Select Bar Chart", chart_options)

if selected_chart == "Monthly Rainfall":
    selected_month = st.sidebar.selectbox("Select Month", months)
    selected_index = months.index(selected_month)
    st.session_state.bar_colors[selected_index] = st.sidebar.color_picker(
        f"{selected_month} Bar Colour",
        st.session_state.bar_colors[selected_index]
    )
elif selected_chart == "Maximum Daily Rainfall":
    st.session_state.max_daily_color = st.sidebar.color_picker(
        "Maximum Daily Rainfall Colour",
        st.session_state.max_daily_color
    )
elif selected_chart == "Wet Days":
    st.session_state.wet_days_color = st.sidebar.color_picker(
        "Wet Days Colour",
        st.session_state.wet_days_color
    )
elif selected_chart == "Standard Deviation":
    st.session_state.std_color = st.sidebar.color_picker(
        "Standard Deviation Colour",
        st.session_state.std_color
    )
elif selected_chart == "Histogram":
    st.session_state.hist_color = st.sidebar.color_picker(
        "Histogram Colour",
        st.session_state.hist_color
    )

LINE_COLOR = st.sidebar.color_picker("Mean Line", "#000000")
MIN_COLOR = st.sidebar.color_picker("Minimum", "#008000")
MAX_COLOR = st.sidebar.color_picker("Maximum", "#FF0000")

FIG_WIDTH = 14
FIG_HEIGHT = 9

# ============================================================
# FILE UPLOAD
# ============================================================

uploaded_files = st.file_uploader(
    "📁 Upload Excel file data hujan AAWS (Fail Mentah atau Fail Terformat):",
    type=["xlsx", "xls"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.info("Sila upload sekurang-kurangnya satu fail Excel.")
    st.markdown(
        """
        **Sistem kini menyokong 2 jenis format secara automatik:**
        1. **Fail Mentah AAWS:** Mempunyai helaian (*sheets*) nama stesen dengan 4 lajur (Year, Month, Day, Rainfall).
        2. **Fail Matriks Terformat:** Helaian dinamakan mengikut tahun (`2016`, `2017`...) dengan jadual 31x12.
        """
    )
    st.stop()

# ============================================================
# ENJIN PEMBACAAN & PENGECAMAN DATA HYBRID
# ============================================================

def max_consecutive_missing(values):
    is_missing = values.isna()
    max_missing, current_missing = 0, 0
    for missing in is_missing:
        if missing:
            current_missing += 1
            if current_missing > max_missing:
                max_missing = current_missing
        else:
            current_missing = 0
    return max_missing

def read_raw_station_sheet(raw_df, sheet_name):
    """Mengekstrak data siri masa daripada fail mentah AAWS 4 lajur"""
    start_row = 11
    for r in range(min(15, len(raw_df))):
        row_txt = " ".join([str(x).lower() for x in raw_df.iloc[r].tolist() if pd.notna(x)])
        if ("year" in row_txt or "tahun" in row_txt) and ("month" in row_txt or "bulan" in row_txt):
            start_row = r + 1
            break

    # Cari nama stesen di bahagian header
    st_name = ""
    for r in range(min(10, len(raw_df))):
        for c in range(min(6, len(raw_df.columns))):
            cell_str = str(raw_df.iloc[r, c]).strip()
            if any(k in cell_str.lower() for k in ['station', 'stesen', 'stn']):
                if ':' in cell_str and len(cell_str.split(':', 1)[1].strip()) > 1:
                    st_name = cell_str.split(':', 1)[1].strip()
                elif c + 1 < len(raw_df.columns) and pd.notna(raw_df.iloc[r, c + 1]):
                    st_name = str(raw_df.iloc[r, c + 1]).strip()
    if not st_name:
        st_name = str(sheet_name).strip()
    st_name = re.sub(r'[<>:"/\\|?*]', '', st_name).strip()

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

    # Ubah format kepada bentuk wide matriks (hari x bulan) mengikut tahun
    daily_dfs = []
    for yr in sorted(data["Year"].unique()):
        df_yr = data[data["Year"] == yr]
        pivot = df_yr.pivot(index="Day", columns="Month", values="Rainfall").reindex(index=range(1, 32), columns=range(1, 13))
        pivot.columns = months
        pivot.insert(0, "hari", pivot.index)
        pivot["Year"] = int(yr)
        daily_dfs.append(pivot)

    return st_name, pd.concat(daily_dfs, ignore_index=True) if daily_dfs else None

def read_year_matrix_sheet(uploaded_file, year):
    """Membaca helaian bertab tahun (Format asal App 1)"""
    file_bytes = uploaded_file.getvalue()
    file_ext = os.path.splitext(uploaded_file.name)[1].lower()
    engine = "xlrd" if file_ext == ".xls" else "openpyxl"
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=str(year), header=6, engine=engine)

    if df is None or df.empty or df.shape[1] < 13:
        return None, "Format matriks tahun tidak sah."

    df = df.iloc[:, :13].copy()
    df.columns = ["hari"] + months
    df["hari"] = pd.to_numeric(df["hari"], errors="coerce")
    df = df[df["hari"].between(1, 31)].copy()

    for m in months:
        df[m] = pd.to_numeric(df[m], errors="coerce")
        df.loc[df[m] < VALID_MIN, m] = np.nan

    df["Year"] = int(year)
    return df, None

def analyze_station_data(station_name, all_daily):
    for month in months:
        all_daily.loc[all_daily[month] < VALID_MIN, month] = np.nan

    suspect_records, extreme_records = [], []
    for _, row in all_daily.iterrows():
        year, day = int(row["Year"]), int(row["hari"])
        for month in months:
            value = row[month]
            if pd.isna(value): continue
            if value > EXTREME_RAINFALL:
                extreme_records.append({"Year": year, "Day": day, "Month": month, "Rainfall (mm)": value, "Status": "EXTREME - DOUBLE CHECK"})
            elif value > SUSPECT_RAINFALL:
                suspect_records.append({"Year": year, "Day": day, "Month": month, "Rainfall (mm)": value, "Status": "SUSPECT - SEMAK"})

    suspect_df = pd.DataFrame(suspect_records, columns=["Year", "Day", "Month", "Rainfall (mm)", "Status"])
    extreme_df = pd.DataFrame(extreme_records, columns=["Year", "Day", "Month", "Rainfall (mm)", "Status"])

    available_years = sorted(all_daily["Year"].unique())
    yearly_monthly_total = pd.DataFrame(index=available_years, columns=months, dtype=float)
    monthly_missing_count = pd.DataFrame(index=available_years, columns=months, dtype=float)
    monthly_valid_count = pd.DataFrame(index=available_years, columns=months, dtype=float)
    monthly_max_consecutive_missing = pd.DataFrame(index=available_years, columns=months, dtype=float)
    monthly_qc_status = pd.DataFrame(index=available_years, columns=months, dtype=object)

    for year in available_years:
        year_data = all_daily[all_daily["Year"] == year]
        for month in months:
            m_idx = months.index(month) + 1
            days_expected = calendar.monthrange(int(year), m_idx)[1]
            values = year_data[month].iloc[:days_expected].copy()
            valid_values = values[values.notna() & (values >= VALID_MIN)]
            valid_count = len(valid_values)
            missing_count = days_expected - valid_count
            max_consecutive = max_consecutive_missing(values)

            monthly_valid_count.loc[year, month] = valid_count
            monthly_missing_count.loc[year, month] = missing_count
            monthly_max_consecutive_missing.loc[year, month] = max_consecutive

            if missing_count <= MAX_MISSING_DAYS and max_consecutive <= MAX_CONSECUTIVE_MISSING:
                yearly_monthly_total.loc[year, month] = valid_values.sum()
                monthly_qc_status.loc[year, month] = "ACCEPT"
            else:
                yearly_monthly_total.loc[year, month] = np.nan
                if missing_count > MAX_MISSING_DAYS:
                    monthly_qc_status.loc[year, month] = f"REJECT: >{MAX_MISSING_DAYS} MISSING"
                elif max_consecutive > MAX_CONSECUTIVE_MISSING:
                    monthly_qc_status.loc[year, month] = f"REJECT: >{MAX_CONSECUTIVE_MISSING} CONSECUTIVE MISSING"
                else:
                    monthly_qc_status.loc[year, month] = "REJECT"

    # Fallback target year jika tiada dalam rekod
    current_target_year = target_year if target_year in yearly_monthly_total.index else (available_years[-1] if available_years else target_year)

    rainfall_target = yearly_monthly_total.loc[current_target_year].reindex(months) if current_target_year in yearly_monthly_total.index else pd.Series(np.nan, index=months)
    mean_monthly_total = yearly_monthly_total.mean(axis=0, skipna=True).reindex(months)

    anomaly_percent = ((rainfall_target - mean_monthly_total) / mean_monthly_total) * 100
    anomaly_percent[mean_monthly_total == 0] = np.nan

    valid_target = rainfall_target.dropna()
    min_target_month, min_target_value = (valid_target.idxmin(), valid_target.min()) if len(valid_target) > 0 else (None, None)
    max_target_month, max_target_value = (valid_target.idxmax(), valid_target.max()) if len(valid_target) > 0 else (None, None)

    valid_mean = mean_monthly_total.dropna()
    min_mean_month, min_mean_value = (valid_mean.idxmin(), valid_mean.min()) if len(valid_mean) > 0 else (None, None)
    max_mean_month, max_mean_value = (valid_mean.idxmax(), valid_mean.max()) if len(valid_mean) > 0 else (None, None)

    median_daily, std_daily, max_daily, min_daily, wet_days, valid_data_percent, suspect_count, extreme_count = [], [], [], [], [], [], [], []
    target_data = all_daily[all_daily["Year"] == current_target_year].copy()

    for month in months:
        m_idx = months.index(month) + 1
        days_expected = calendar.monthrange(current_target_year, m_idx)[1] if current_target_year else 31
        raw_values = target_data[month].iloc[:days_expected].copy() if not target_data.empty else pd.Series()
        qc_values = raw_values[raw_values.notna() & (raw_values >= VALID_MIN)]
        values = qc_values[qc_values >= WET_DAY_MIN]

        valid_data_percent.append((len(qc_values) / days_expected) * 100 if days_expected else 0)
        median_daily.append(values.median() if len(values) > 0 else np.nan)
        std_daily.append(values.std() if len(values) > 1 else np.nan)
        max_daily.append(values.max() if len(values) > 0 else np.nan)
        min_daily.append(values.min() if len(values) > 0 else np.nan)
        wet_days.append((qc_values >= WET_DAY_MIN).sum())
        suspect_count.append((values > SUSPECT_RAINFALL).sum())
        extreme_count.append((values > EXTREME_RAINFALL).sum())

    analysis_table = pd.DataFrame({
        "Month": months,
        f"Total {current_target_year} (mm)": rainfall_target.values,
        f"Mean {YEAR_RANGE_TEXT} (mm)": mean_monthly_total.values,
        f"Anomaly {current_target_year} (%)": anomaly_percent.values,
        "Median Daily (>=0.1 mm)": median_daily,
        "SD Daily (>=0.1 mm)": std_daily,
        "Maximum Daily (>=0.1 mm)": max_daily,
        "Minimum Daily (>=0.1 mm)": min_daily,
        "Wet Days (>=0.1 mm)": wet_days,
        "Suspect Days (>150 mm)": suspect_count,
        "Extreme Days (>250 mm)": extreme_count,
        "Valid Data (>=0.0 mm) (%)": valid_data_percent
    })

    hist_values, pie_values = [], []
    for month in months:
        m_idx = months.index(month) + 1
        days_expected = calendar.monthrange(current_target_year, m_idx)[1] if current_target_year else 31
        raw_values = target_data[month].iloc[:days_expected].copy() if not target_data.empty else pd.Series()
        values = raw_values[raw_values.notna() & (raw_values >= VALID_MIN)]
        pie_values.extend(values.tolist())
        hist_values.extend(values[values >= WET_DAY_MIN].tolist())

    no_rain = sum(v == 0.0 for v in pie_values)
    light_rain = sum(0.1 <= v <= 2.5 for v in pie_values)
    moderate_rain = sum(2.5 < v <= 10.0 for v in pie_values)
    heavy_rain = sum(10.0 < v <= 50.0 for v in pie_values)
    extreme_rain = sum(v > 50.0 for v in pie_values)

    return {
        "success": True,
        "file_name": station_name,
        "original_file_name": station_name,
        "all_daily": all_daily,
        "yearly_monthly_total": yearly_monthly_total,
        "monthly_missing_count": monthly_missing_count,
        "monthly_valid_count": monthly_valid_count,
        "monthly_max_consecutive_missing": monthly_max_consecutive_missing,
        "monthly_qc_status": monthly_qc_status,
        "rainfall_target": rainfall_target,
        "mean_monthly_total": mean_monthly_total,
        "anomaly_percent": anomaly_percent,
        "min_target_month": min_target_month, "min_target_value": min_target_value,
        "max_target_month": max_target_month, "max_target_value": max_target_value,
        "min_mean_month": min_mean_month, "min_mean_value": min_mean_value,
        "max_mean_month": max_mean_month, "max_mean_value": max_mean_value,
        "median_daily": median_daily, "std_daily": std_daily, "max_daily": max_daily, "min_daily": min_daily,
        "wet_days": wet_days, "valid_data_percent": valid_data_percent,
        "suspect_count": suspect_count, "extreme_count": extreme_count,
        "analysis_table": analysis_table, "suspect_df": suspect_df, "extreme_df": extreme_df,
        "hist_values": hist_values, "category_values": [no_rain, light_rain, moderate_rain, heavy_rain, extreme_rain],
        "category_labels": ["No Rain (0.0 mm)", "Light Rain (0.1–2.5 mm)", "Moderate Rain (>2.5–10.0 mm)", "Heavy Rain (>10.0-50.0 mm)", "Extreme Rain (>50 mm)"],
        "read_errors": []
    }

# ============================================================
# PEMPROSESAN FAIL SECARA DINAMIK
# ============================================================

with st.spinner("⏳ Sedang membaca dan memproses data AAWS..."):
    results = []
    
    for uploaded_file in uploaded_files:
        try:
            excel = pd.ExcelFile(uploaded_file)
            sheet_names = excel.sheet_names
            
            # Semak sama ada ini fail matriks tahunan atau fail raw AAWS stesen
            year_sheets = [s for s in sheet_names if str(s).strip().isdigit() and int(str(s).strip()) in years]
            
            if len(year_sheets) > 0:
                # Format Matriks Tahunan (Fail output ekstraksi)
                daily_results = []
                for yr in years:
                    df, err = read_year_matrix_sheet(uploaded_file, yr)
                    if df is not None: daily_results.append(df)
                if daily_results:
                    combined = pd.concat(daily_results, ignore_index=True)
                    res = analyze_station_data(os.path.splitext(uploaded_file.name)[0], combined)
                    results.append(res)
            else:
                # Format Fail Mentah AAWS (Berbilang sheet mengikut stesen)
                for s_name in sheet_names:
                    if str(s_name).lower().strip() in ['datalist', 'info', 'summary', 'sheet1']:
                        continue
                    raw_df = pd.read_excel(uploaded_file, sheet_name=s_name, header=None)
                    st_name, st_daily = read_raw_station_sheet(raw_df, s_name)
                    if st_daily is not None:
                        res = analyze_station_data(st_name, st_daily)
                        results.append(res)
        except Exception as e:
            st.error(f"Ralat memproses {uploaded_file.name}: {e}")

successful_results = [r for r in results if r.get("success", False)]

if not successful_results:
    st.error("⚠️ Tiada stesen atau data tahun sah yang berjaya dikesan daripada fail yang dimuat naik.")
    st.stop()

st.success(f"✅ Sebanyak **{len(successful_results)} stesen cerapan** berjaya dikesan & dianalisis sepenuhnya!")

# ============================================================
# GLOBAL AUTO Y-AXIS
# ============================================================

global_max_total, global_max_mean = 0, 0
max_total_file, max_total_month = None, None
max_mean_file, max_mean_month = None, None

for result in successful_results:
    rainfall_target = result["rainfall_target"]
    mean_monthly_total = result["mean_monthly_total"]
    if rainfall_target.notna().any():
        local_max = rainfall_target.max()
        if local_max > global_max_total:
            global_max_total = local_max
            max_total_file = result["original_file_name"]
            max_total_month = rainfall_target.idxmax()
    if mean_monthly_total.notna().any():
        local_max = mean_monthly_total.max()
        if local_max > global_max_mean:
            global_max_mean = local_max
            max_mean_file = result["original_file_name"]
            max_mean_month = mean_monthly_total.idxmax()

selected_max = max(global_max_total, global_max_mean)
RAINFALL_MAX = (int(selected_max / 100) + 1) * 100 if selected_max > 0 else 100

# ============================================================
# GLOBAL SUMMARY
# ============================================================

st.subheader("📌 Ringkasan Keseluruhan Operasi")
summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
summary_col1.metric("Stesen Dikesan", len(successful_results))
summary_col2.metric("Target Year", target_year)
summary_col3.metric("Tempoh Normal", YEAR_RANGE_TEXT)
summary_col4.metric("Skala Maks. Paksi Y", f"{RAINFALL_MAX:.0f} mm")

# ============================================================
# MULTI-STATION OVERLAY COMPARISON
# ============================================================
if len(successful_results) >= 2:
    with st.expander("📊 Perbandingan Merentas Berbilang Stesen (Multi-Station Overlay)", expanded=False):
        st_names = [r["file_name"] for r in successful_results]
        selected_multi = st.multiselect("Pilih stesen untuk perbandingan profil bulanan:", st_names, default=st_names[:min(4, len(st_names))])
        
        if len(selected_multi) >= 2:
            comp_fig = go.Figure()
            for s_name in selected_multi:
                s_res = next(r for r in successful_results if r["file_name"] == s_name)
                comp_fig.add_trace(go.Scatter(
                    x=months,
                    y=s_res["mean_monthly_total"].values,
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

# ============================================================
# PAPARAN SETIAP STESEN (11 TAB ASAL APP 1 KEBERADAAN 100%)
# ============================================================

for result in successful_results:
    file_name = result["file_name"]
    original_file_name = result["original_file_name"]
    all_daily = result["all_daily"]
    yearly_monthly_total = result["yearly_monthly_total"]
    monthly_missing_count = result["monthly_missing_count"]
    monthly_valid_count = result["monthly_valid_count"]
    monthly_max_consecutive_missing = result["monthly_max_consecutive_missing"]
    monthly_qc_status = result["monthly_qc_status"]
    rainfall_target = result["rainfall_target"]
    mean_monthly_total = result["mean_monthly_total"]
    anomaly_percent = result["anomaly_percent"]
    min_target_month = result["min_target_month"]
    min_target_value = result["min_target_value"]
    max_target_month = result["max_target_month"]
    max_target_value = result["max_target_value"]
    min_mean_month = result["min_mean_month"]
    min_mean_value = result["min_mean_value"]
    max_mean_month = result["max_mean_month"]
    max_mean_value = result["max_mean_value"]
    median_daily = result["median_daily"]
    std_daily = result["std_daily"]
    max_daily = result["max_daily"]
    min_daily = result["min_daily"]
    wet_days = result["wet_days"]
    valid_data_percent = result["valid_data_percent"]
    analysis_table = result["analysis_table"]
    suspect_df = result["suspect_df"]
    extreme_df = result["extreme_df"]
    hist_values = result["hist_values"]
    category_values = result["category_values"]
    category_labels = result["category_labels"]

    st.divider()
    st.header(f"📍 Stesen: {original_file_name}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(f"Minimum {target_year}", f"{min_target_value:.2f} mm" if min_target_value is not None else "N.A.", min_target_month)
    col2.metric(f"Maximum {target_year}", f"{max_target_value:.2f} mm" if max_target_value is not None else "N.A.", max_target_month)
    col3.metric("Minimum Mean", f"{min_mean_value:.2f} mm" if min_mean_value is not None else "N.A.", min_mean_month)
    col4.metric("Maximum Mean", f"{max_mean_value:.2f} mm" if max_mean_value is not None else "N.A.", max_mean_month)

    qc_col1, qc_col2, qc_col3 = st.columns(3)
    qc_col1.metric("Suspect Records (>150mm)", len(suspect_df))
    qc_col2.metric("Extreme Records (>250mm)", len(extreme_df))
    qc_col3.metric("Valid Daily Records", int(all_daily[months].notna().sum().sum()))

    view_mode = st.radio(
        f"Pilih Mod Paparan Bagi {file_name}:",
        ["📊 Paparan Penuh Standard (11 Tab Analisis Lengkap)", "🌐 Pandangan Umum (Public Dashboard)", "🔬 Analisis Trend Saintifik (Regresi Linear)"],
        horizontal=True,
        key=f"mode_{file_name}"
    )

    if view_mode == "🌐 Pandangan Umum (Public Dashboard)":
        st.subheader(f"🌐 Ringkasan Iklim Mesra Awam — {file_name}")
        valid_means = mean_monthly_total.dropna()
        if len(valid_means) > 0:
            wet_m, dry_m = valid_means.idxmax(), valid_means.idxmin()
            c_p1, c_p2, c_p3 = st.columns(3)
            c_p1.metric("Purata Hujan Tahunan", f"{valid_means.sum():.1f} mm")
            c_p2.metric("Bulan Paling Basah", f"{wet_m} ({valid_means.max():.1f} mm)")
            c_p3.metric("Bulan Paling Kering", f"{dry_m} ({valid_means.min():.1f} mm)")

            cp_left, cp_right = st.columns([6, 4])
            with cp_left:
                fig_pub = px.bar(x=months, y=mean_monthly_total.values, text=mean_monthly_total.values, labels={'x':'Bulan', 'y':'Purata Hujan (mm)'}, title="Purata Penerimaan Hujan Bulanan")
                fig_pub.update_traces(texttemplate='%{text:.1f} mm', textposition='outside')
                st.plotly_chart(fig_pub, use_container_width=True)
            with cp_right:
                tot_days = sum(category_values)
                rain_days = tot_days - category_values[0]
                donut_df = pd.DataFrame({'Kategori': ['Hari Berhujan (≥0.1mm)', 'Hari Kering (0.0mm)'], 'Jumlah': [rain_days, category_values[0]]})
                st.plotly_chart(px.pie(donut_df, names='Kategori', values='Jumlah', hole=0.5, color_discrete_sequence=['#1f77b4', '#ffa500']), use_container_width=True)

    elif view_mode == "🔬 Analisis Trend Saintifik (Regresi Linear)":
        st.subheader(f"🔬 Analisis Trend Jangka Panjang — {file_name}")
        ann_totals = yearly_monthly_total.sum(axis=1, min_count=10).dropna().reset_index()
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
        # ====================================================
        # 11 TAB ASAL KOD APP (1) DIKEKALKAN 100%
        # ====================================================
        tabs = st.tabs([
            "📊 Bar + Line", "🔥 Heatmap", "📉 Anomaly", "📋 Statistics",
            "📈 Max Daily", "🌧️ Wet Days", "📐 Standard Deviation",
            "📊 Histogram", "🥧 Rainfall Category", "📦 Boxplot", "⚠️ QC"
        ])

        target_data = all_daily[all_daily["Year"] == target_year].copy()

        # TAB 1: BAR + LINE
        with tabs[0]:
            st.subheader(f"Monthly Rainfall {target_year} vs Mean Monthly Rainfall {YEAR_RANGE_TEXT}")
            x = np.arange(len(months))
            fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
            fig.patch.set_facecolor(BG_COLOR)
            ax.set_facecolor(BG_COLOR)

            ax.bar(x, rainfall_target.values, width=0.60, color=st.session_state.bar_colors, edgecolor="black", linewidth=0.8, label=f"Total Rainfall {target_year}")
            ax.plot(x, mean_monthly_total.values, color=LINE_COLOR, marker="o", linewidth=2.5, markersize=7, label=f"Mean Monthly Rainfall {YEAR_RANGE_TEXT}")

            for i, value in enumerate(mean_monthly_total.values):
                if pd.notna(value):
                    ax.annotate(f"{value:.1f}", (i, value), xytext=(0, 10), textcoords="offset points", ha="center", fontsize=11, fontweight="bold")

            if min_target_month is not None:
                min_index = months.index(min_target_month)
                ax.scatter(min_index, min_target_value, s=50, color=MIN_COLOR, edgecolor="black", linewidth=1, zorder=5, label=f"Minimum {target_year}: {min_target_month} ({min_target_value:.1f} mm)")

            if max_target_month is not None:
                max_index = months.index(max_target_month)
                ax.scatter(max_index, max_target_value, s=50, color=MAX_COLOR, edgecolor="black", linewidth=1, zorder=5, label=f"Maximum {target_year}: {max_target_month} ({max_target_value:.1f} mm)")

            ax.set_title(f"{file_name}\nMonthly Rainfall {target_year} vs Mean Monthly Rainfall {YEAR_RANGE_TEXT}", fontsize=16, fontweight="bold")
            ax.set_xlabel("Month", fontsize=12)
            ax.set_ylabel("Rainfall (mm)", fontsize=12)
            ax.set_xticks(x)
            ax.set_xticklabels(months)
            ax.set_ylim(RAINFALL_MIN, RAINFALL_MAX)
            ax.grid(True, axis="y", linestyle="--", alpha=0.4)
            ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9)
            plt.tight_layout()
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)

        # TAB 2: HEATMAP
        with tabs[1]:
            st.subheader(f"Monthly Total Rainfall Heatmap {YEAR_RANGE_TEXT}")
            plot_data = yearly_monthly_total.reindex(columns=months)
            fig, ax = plt.subplots(figsize=(14, 8))
            fig.patch.set_facecolor(BG_COLOR)
            ax.set_facecolor(BG_COLOR)

            valid_values = plot_data.values[~pd.isna(plot_data.values)]
            vmin, vmax = (valid_values.min(), valid_values.max()) if len(valid_values) > 0 else (0, 1)
            if vmin == vmax: vmax = vmin + 1

            im = ax.imshow(plot_data.values, aspect="auto", cmap="YlGnBu", vmin=vmin, vmax=vmax)
            ax.set_xticks(range(len(months)))
            ax.set_xticklabels(months)
            ax.set_yticks(range(len(plot_data.index)))
            ax.set_yticklabels(plot_data.index.astype(str))

            for i in range(len(plot_data.index)):
                for j in range(len(months)):
                    val = plot_data.iloc[i, j]
                    if pd.notna(val):
                        ax.text(j, i, f"{val:.0f}", ha="center", va="center", fontsize=7)
                    else:
                        ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, facecolor="lightgray", edgecolor="white", linewidth=1))
                        ax.text(j, i, "N.A.", ha="center", va="center", fontsize=7)

            fig.colorbar(im, ax=ax).set_label("Total Rainfall (mm)", fontsize=11)
            ax.set_title(f"{file_name}\nMonthly Total Rainfall Heatmap, {YEAR_RANGE_TEXT}", fontsize=16, fontweight="bold")
            plt.tight_layout()
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)

        # TAB 3: ANOMALY
        with tabs[2]:
            st.subheader(f"Rainfall Anomaly {target_year} Relative to Mean {YEAR_RANGE_TEXT}")
            fig, ax = plt.subplots(figsize=(14, 8))
            fig.patch.set_facecolor(BG_COLOR)
            ax.set_facecolor(BG_COLOR)

            anomaly_colors = ["lightgray" if pd.isna(v) else ("darkorange" if v >= 0 else "steelblue") for v in anomaly_percent.values]
            bars = ax.bar(x, anomaly_percent.values, width=0.60, color=anomaly_colors, edgecolor="black", linewidth=0.8)
            ax.axhline(0, color="black", linewidth=1)

            for bar, val in zip(bars, anomaly_percent.values):
                if pd.notna(val):
                    offset, vertical = (4, "bottom") if val >= 0 else (-12, "top")
                    ax.annotate(f"{val:.1f}%", (bar.get_x() + bar.get_width() / 2, val), xytext=(0, offset), textcoords="offset points", ha="center", va=vertical, fontsize=8)

            ax.set_title(f"{file_name}\nRainfall Anomaly {target_year} Relative to Mean {YEAR_RANGE_TEXT}", fontsize=16, fontweight="bold")
            ax.set_xlabel("Month", fontsize=12)
            ax.set_ylabel("Anomaly (%)", fontsize=12)
            ax.set_xticks(x)
            ax.set_xticklabels(months)
            ax.grid(True, axis="y", linestyle="--", alpha=0.4)
            plt.tight_layout()
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)

        # TAB 4: STATISTICS
        with tabs[3]:
            st.subheader("📋 Rainfall Statistical Analysis")
            display_table = analysis_table.copy()
            for col in display_table.columns[display_table.columns != "Month"]:
                display_table[col] = pd.to_numeric(display_table[col], errors="coerce").round(2)
            st.dataframe(display_table, use_container_width=True, hide_index=True)
            st.download_button(
                "📥 Download Statistical Analysis CSV",
                analysis_table.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"{file_name}_Statistical_Analysis_{YEAR_RANGE_TEXT}.csv",
                mime="text/csv"
            )

        # TAB 5: MAX DAILY
        with tabs[4]:
            st.subheader(f"Maximum Daily Rainfall by Month - {target_year}")
            fig, ax = plt.subplots(figsize=(14, 8))
            fig.patch.set_facecolor(BG_COLOR)
            ax.set_facecolor(BG_COLOR)
            bars = ax.bar(x, max_daily, width=0.60, color=st.session_state.max_daily_color, edgecolor="black", linewidth=0.8)
            for bar, val in zip(bars, max_daily):
                if pd.notna(val): ax.annotate(f"{val:.1f}", (bar.get_x() + bar.get_width()/2, val), xytext=(0, 6), textcoords="offset points", ha="center", fontsize=10, fontweight="bold")
            ax.set_title(f"{file_name}\nMaximum Daily Rainfall by Month - {target_year}", fontsize=16, fontweight="bold")
            ax.set_xticks(x)
            ax.set_xticklabels(months)
            ax.grid(True, axis="y", linestyle="--", alpha=0.4)
            plt.tight_layout()
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)

        # TAB 6: WET DAYS
        with tabs[5]:
            st.subheader(f"Number of Wet Days (≥0.1 mm) - {target_year}")
            fig, ax = plt.subplots(figsize=(14, 8))
            fig.patch.set_facecolor(BG_COLOR)
            ax.set_facecolor(BG_COLOR)
            bars = ax.bar(x, wet_days, width=0.60, color=st.session_state.wet_days_color, edgecolor="black", linewidth=0.8)
            for bar, val in zip(bars, wet_days):
                if pd.notna(val): ax.annotate(f"{int(val)}", (bar.get_x() + bar.get_width()/2, val), xytext=(0, 6), textcoords="offset points", ha="center", fontsize=10, fontweight="bold")
            ax.set_title(f"{file_name}\nNumber of Wet Days (≥0.1 mm) - {target_year}", fontsize=16, fontweight="bold")
            ax.set_xticks(x)
            ax.set_xticklabels(months)
            ax.grid(True, axis="y", linestyle="--", alpha=0.4)
            plt.tight_layout()
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)

        # TAB 7: STANDARD DEVIATION
        with tabs[6]:
            st.subheader(f"Daily Rainfall Standard Deviation - {target_year}")
            fig, ax = plt.subplots(figsize=(14, 8))
            fig.patch.set_facecolor(BG_COLOR)
            ax.set_facecolor(BG_COLOR)
            bars = ax.bar(x, std_daily, width=0.60, color=st.session_state.std_color, edgecolor="black", linewidth=0.8)
            for bar, val in zip(bars, std_daily):
                if pd.notna(val): ax.annotate(f"{val:.1f}", (bar.get_x() + bar.get_width()/2, val), xytext=(0, 6), textcoords="offset points", ha="center", fontsize=10, fontweight="bold")
            ax.set_title(f"{file_name}\nDaily Rainfall Standard Deviation - {target_year}", fontsize=16, fontweight="bold")
            ax.set_xticks(x)
            ax.set_xticklabels(months)
            ax.grid(True, axis="y", linestyle="--", alpha=0.4)
            plt.tight_layout()
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)

        # TAB 8: HISTOGRAM
        with tabs[7]:
            st.subheader(f"Distribution of Daily Rainfall - {target_year}")
            if len(hist_values) > 0:
                fig, ax = plt.subplots(figsize=(14, 8))
                fig.patch.set_facecolor(BG_COLOR)
                ax.set_facecolor(BG_COLOR)
                ax.hist(hist_values, bins=15, color=st.session_state.hist_color, edgecolor="black", linewidth=0.8)
                ax.set_title(f"{file_name}\nDistribution of Daily Rainfall - {target_year}", fontsize=16, fontweight="bold")
                ax.set_xlabel("Daily Rainfall (mm)", fontsize=12)
                ax.set_ylabel("Number of Days", fontsize=12)
                ax.grid(True, axis="y", linestyle="--", alpha=0.4)
                plt.tight_layout()
                st.pyplot(fig, use_container_width=True)
                plt.close(fig)
            else:
                st.warning("Tiada data hujan ≥ 0.1 mm untuk histogram.")

        # TAB 9: RAINFALL CATEGORY
        with tabs[8]:
            st.subheader(f"Percentage of Days by Rainfall Category - {target_year}")
            if sum(category_values) > 0:
                fig, ax = plt.subplots(figsize=(10, 8))
                fig.patch.set_facecolor(BG_COLOR)
                ax.set_facecolor(BG_COLOR)
                wedges, texts, autotexts = ax.pie(category_values, labels=category_labels, autopct="%1.1f%%", startangle=90, counterclock=False, wedgeprops={"edgecolor":"black", "linewidth":0.8})
                for at in autotexts: at.set_fontsize(11); at.set_fontweight("bold")
                ax.set_title(f"{file_name}\nPercentage of Days by Rainfall Category - {target_year}", fontsize=16, fontweight="bold")
                plt.tight_layout()
                st.pyplot(fig, use_container_width=True)
                plt.close(fig)
            else:
                st.warning("Tiada data sah untuk pie chart.")

        # TAB 10: BOXPLOT
        with tabs[9]:
            st.subheader(f"Daily Rainfall Distribution by Month - {target_year}")
            boxplot_data, boxplot_labels = [], []
            for month in months:
                m_idx = months.index(month) + 1
                days_expected = calendar.monthrange(target_year, m_idx)[1] if target_year else 31
                vals = target_data[month].iloc[:days_expected].dropna() if not target_data.empty else pd.Series()
                boxplot_data.append(vals[vals >= WET_DAY_MIN].tolist())
                boxplot_labels.append(month)

            if any(len(v) > 0 for v in boxplot_data):
                fig, ax = plt.subplots(figsize=(14, 8))
                fig.patch.set_facecolor(BG_COLOR)
                ax.set_facecolor(BG_COLOR)
                bp = ax.boxplot(boxplot_data, tick_labels=boxplot_labels, patch_artist=True, showmeans=True, meanline=False, showfliers=True)
                for box in bp["boxes"]: box.set(facecolor="#87CEEB", edgecolor="black", linewidth=1)
                for median in bp["medians"]: median.set(color="red", linewidth=2)
                for mean in bp["means"]: mean.set(marker="o", markerfacecolor="black", markeredgecolor="black", markersize=5)
                ax.set_title(f"{file_name}\nDaily Rainfall Distribution by Month - {target_year}", fontsize=16, fontweight="bold")
                ax.grid(True, axis="y", linestyle="--", alpha=0.4)
                plt.tight_layout()
                st.pyplot(fig, use_container_width=True)
                plt.close(fig)
            else:
                st.warning("Tiada data hujan ≥ 0.1 mm untuk boxplot.")

        # TAB 11: QUALITY CONTROL
        with tabs[10]:
            st.subheader("⚠️ Quality Control")
            qc_tabs = st.tabs(["⚠️ Suspect", "🚨 Extreme", "📅 Missing Count", "🔢 Valid Count", "🔁 Consecutive Missing", "📋 QC Status"])
            with qc_tabs[0]:
                st.write(f"Jumlah suspect rainfall > {SUSPECT_RAINFALL:.0f} mm: **{len(suspect_df)}**")
                if len(suspect_df) > 0:
                    st.dataframe(suspect_df, use_container_width=True, hide_index=True)
                    st.download_button("📥 Download Suspect CSV", suspect_df.to_csv(index=False).encode("utf-8-sig"), f"{file_name}_Suspect.csv", "text/csv")
                else:
                    st.success("Tiada rainfall suspect dikesan.")
            with qc_tabs[1]:
                st.write(f"Jumlah extreme rainfall > {EXTREME_RAINFALL:.0f} mm: **{len(extreme_df)}**")
                if len(extreme_df) > 0:
                    st.dataframe(extreme_df, use_container_width=True, hide_index=True)
                    st.download_button("📥 Download Extreme CSV", extreme_df.to_csv(index=False).encode("utf-8-sig"), f"{file_name}_Extreme.csv", "text/csv")
                else:
                    st.success("Tiada rainfall extreme dikesan.")
            with qc_tabs[2]: st.dataframe(monthly_missing_count, use_container_width=True)
            with qc_tabs[3]: st.dataframe(monthly_valid_count, use_container_width=True)
            with qc_tabs[4]: st.dataframe(monthly_max_consecutive_missing, use_container_width=True)
            with qc_tabs[5]: st.dataframe(monthly_qc_status, use_container_width=True)

# ============================================================
# DOWNLOAD ALL RESULTS AS ZIP
# ============================================================

st.divider()
st.header("📦 Download Analysis Results")
st.write("Muat turun semua jadual analisis, QC dan data suspect/extreme sebagai satu fail ZIP.")

zip_buffer = io.BytesIO()
with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
    for result in successful_results:
        fn = result["file_name"]
        zip_file.writestr(f"{fn}/{fn}_Statistical_Analysis_{YEAR_RANGE_TEXT}.csv", result["analysis_table"].to_csv(index=False))
        zip_file.writestr(f"{fn}/{fn}_Monthly_Total_{YEAR_RANGE_TEXT}.csv", result["yearly_monthly_total"].to_csv())
        zip_file.writestr(f"{fn}/{fn}_Missing_Days_{YEAR_RANGE_TEXT}.csv", result["monthly_missing_count"].to_csv())
        zip_file.writestr(f"{fn}/{fn}_Valid_Days_{YEAR_RANGE_TEXT}.csv", result["monthly_valid_count"].to_csv())
        zip_file.writestr(f"{fn}/{fn}_Consecutive_Missing_{YEAR_RANGE_TEXT}.csv", result["monthly_max_consecutive_missing"].to_csv())
        zip_file.writestr(f"{fn}/{fn}_QC_Status_{YEAR_RANGE_TEXT}.csv", result["monthly_qc_status"].to_csv())
        zip_file.writestr(f"{fn}/{fn}_Suspect_Rainfall.csv", result["suspect_df"].to_csv(index=False))
        zip_file.writestr(f"{fn}/{fn}_Extreme_Rainfall.csv", result["extreme_df"].to_csv(index=False))

zip_buffer.seek(0)
st.download_button(
    label="📦 Download All Results (ZIP)",
    data=zip_buffer.getvalue(),
    file_name=f"Rainfall_Analysis_{YEAR_RANGE_TEXT}_Target_{target_year}.zip",
    mime="application/zip"
)

# ============================================================
# FOOTER
# ============================================================

st.divider()
st.caption("🌧️ Rainfall Data Analysis | Quality Control, Climatological Mean, Anomaly and Statistical Analysis")