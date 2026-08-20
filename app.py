import pandas as pd
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
    page_title="Sistem Analisis Klimatologi AAWS | MetMalaysia Sabah",
    page_icon="🌤️",
    layout="wide"
)

# Custom Styling (Clean Slate UI)
st.markdown("""
    <style>
        .block-container { padding-top: 1.8rem; padding-bottom: 2rem; }
        div[data-testid="stMetricValue"] { font-size: 1.4rem; font-weight: 700; }
        .stTabs [data-baseweb="tab-list"] { gap: 8px; }
        .stTabs [data-baseweb="tab"] {
            border-radius: 8px 8px 0px 0px;
            padding: 8px 16px;
            font-weight: 600;
        }
    </style>
""", unsafe_allow_html=True)

# ============================================================
# 2. HEADER
# ============================================================
head_c1, head_c2 = st.columns([1, 8])
with head_c1:
    st.markdown("<h1 style='font-size: 42px; margin: 0;'>🌤️</h1>", unsafe_allow_html=True)
with head_c2:
    st.markdown("### **Sistem Integrasi Analisis & Klimatologi AAWS**")
    st.caption("Jabatan Meteorologi Malaysia (MetMalaysia) | Pejabat Meteorologi Sabah | Piawaian WMO-No. 1203")

st.divider()

# ============================================================
# 3. SIDEBAR CONTROLS
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
st.sidebar.subheader("🛡️ Piawaian QC & Had WMO")
MAX_MISSING_DAYS = int(st.sidebar.number_input("Maks. Hari Hilang (Sebulan)", min_value=0, max_value=31, value=10, step=1))
MAX_CONSECUTIVE_MISSING = int(st.sidebar.number_input("Maks. Hilang Berturut-turut", min_value=1, max_value=31, value=4, step=1))
WET_DAY_MIN = float(st.sidebar.number_input("Had Hari Berhujan (mm)", min_value=0.0, value=0.1, step=0.01))
SUSPECT_RAINFALL = float(st.sidebar.number_input("Had Suspect (mm)", min_value=0.0, value=150.0, step=10.0))
EXTREME_RAINFALL = float(st.sidebar.number_input("Had Ekstrem (mm)", min_value=0.0, value=250.0, step=10.0))

months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ============================================================
# 4. ENJIN PEMPROSESAN & CACHING PANTAS
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

        suspect_df = data_df[data_df["Rainfall"] > susp_th][["Year", "Month", "Day", "Rainfall"]].copy()
        extreme_df = data_df[data_df["Rainfall"] > extr_th][["Year", "Month", "Day", "Rainfall"]].copy()

        avail_years = sorted(data_df["Year"].unique())
        yearly_monthly_total = pd.DataFrame(index=avail_years, columns=months, dtype=float)
        monthly_qc_status = pd.DataFrame(index=avail_years, columns=months, dtype=object)

        for yr in avail_years:
            yr_df = data_df[data_df["Year"] == yr]
            for m_num, m_name in enumerate(months, start=1):
                days_exp = calendar.monthrange(int(yr), m_num)[1]
                vals = yr_df[yr_df["Month"] == m_num]["Rainfall"]
                v_cnt = vals.notna().sum()
                m_cnt = days_exp - v_cnt
                c_cnt = max_consecutive_missing_vectorized(vals)

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

        # Target Year Stats
        tgt_data = data_df[data_df["Year"] == curr_tgt_yr]
        median_d, max_d, wet_d = [], [], []

        for m_num, m_name in enumerate(months, start=1):
            m_vals = tgt_data[tgt_data["Month"] == m_num]["Rainfall"].dropna()
            w_vals = m_vals[m_vals >= wet_min]
            median_d.append(w_vals.median() if len(w_vals) > 0 else np.nan)
            max_d.append(w_vals.max() if len(w_vals) > 0 else np.nan)
            wet_d.append(len(w_vals))

        analysis_table = pd.DataFrame({
            "Month": months,
            f"Total {curr_tgt_yr} (mm)": rainfall_target.values,
            f"Mean {YEAR_RANGE_TEXT} (mm)": mean_monthly_total.values,
            f"Anomaly {curr_tgt_yr} (%)": anomaly_percent.values,
            "Median Daily (>=0.1mm)": median_d,
            "Maximum Daily (mm)": max_d,
            "Wet Days Count": wet_d
        })

        pie_vals = tgt_data["Rainfall"].dropna().values
        cat_vals = [
            int((pie_vals == 0.0).sum()),
            int(((pie_vals >= 0.1) & (pie_vals <= 2.5)).sum()),
            int(((pie_vals > 2.5) & (pie_vals <= 10.0)).sum()),
            int(((pie_vals > 10.0) & (pie_vals <= 50.0)).sum()),
            int((pie_vals > 50.0).sum())
        ]

        station_results[st_name] = {
            "data_df": data_df,
            "yearly_monthly_total": yearly_monthly_total,
            "rainfall_target": rainfall_target,
            "mean_monthly_total": mean_monthly_total,
            "anomaly_percent": anomaly_percent,
            "analysis_table": analysis_table,
            "suspect_df": suspect_df,
            "extreme_df": extreme_df,
            "target_year": curr_tgt_yr,
            "category_values": cat_vals,
            "hist_values": pie_vals[pie_vals >= wet_min]
        }

    return station_results

# ============================================================
# 5. DATA INGESTION & CENTRAL SELECTION
# ============================================================
uploaded_files = st.file_uploader(
    "📁 Muat naik fail AAWS (.xls / .xlsx):",
    type=["xlsx", "xls"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.info("👈 Sila muat naik fail data AAWS untuk memulakan analisis.")
    st.stop()

files_payload = tuple((f.name, f.getvalue()) for f in uploaded_files)

with st.spinner("⚡ Memproses data siri masa..."):
    station_results = process_all_files(
        files_payload,
        tuple(years),
        target_year,
        MAX_MISSING_DAYS,
        MAX_CONSECUTIVE_MISSING,
        WET_DAY_MIN,
        SUSPECT_RAINFALL,
        EXTREME_RAINFALL
    )

if not station_results:
    st.error("⚠️ Tiada data sah dijumpai.")
    st.stop()

# Station Selector Bar
col_sel, col_info = st.columns([3, 1])
with col_sel:
    selected_station = st.selectbox(
        "📍 **Pilih Stesen Utama:**",
        options=sorted(list(station_results.keys()))
    )
with col_info:
    st.write("")
    st.success(f"**{len(station_results)} Stesen** Sedia Dianalisis")

st_data = station_results[selected_station]
curr_tgt_yr = st_data["target_year"]
valid_means = st_data["mean_monthly_total"].dropna()

# Executive KPI Strip
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Purata Hujan Tahunan", f"{valid_means.sum():.1f} mm" if not valid_means.empty else "N.A.")
k2.metric("Bulan Kemuncak", f"{valid_means.idxmax()} ({valid_means.max():.1f} mm)" if not valid_means.empty else "N.A.")
k3.metric("Bulan Terkering", f"{valid_means.idxmin()} ({valid_means.min():.1f} mm)" if not valid_means.empty else "N.A.")
k4.metric(f"Total Hujan ({curr_tgt_yr})", f"{st_data['rainfall_target'].sum():.1f} mm" if st_data['rainfall_target'].notna().any() else "N.A.")
k5.metric("Rekod Suspect/Ekstrem", f"{len(st_data['suspect_df']) + len(st_data['extreme_df'])} Hari")

st.markdown("---")

# ============================================================
# 6. MAIN WORKSPACE (STREAMLINED 3-TIER TABS)
# ============================================================
tab_public, tab_scientific, tab_multi, tab_data = st.tabs([
    "🌐 1. Dashboard Awam",
    "🔬 2. Analisis Saintifik & WMO",
    "📊 3. Perbandingan Rentas Stesen",
    "📋 4. Jadual & Muat Turun"
])

# ------------------------------------------------------------
# TIER 1: DASHBOARD AWAM
# ------------------------------------------------------------
with tab_public:
    c_left, c_right = st.columns([6, 4])
    with c_left:
        fig_bar = px.bar(
            x=months,
            y=st_data["mean_monthly_total"].values,
            text=st_data["mean_monthly_total"].values,
            labels={'x': 'Bulan', 'y': 'Hujan (mm)'},
            title=f"Profil Purata Hujan Bulanan Normal ({YEAR_RANGE_TEXT})",
            color=st_data["mean_monthly_total"].values,
            color_continuous_scale="Blues"
        )
        fig_bar.update_traces(texttemplate='%{text:.1f} mm', textposition='outside')
        fig_bar.update_layout(height=420, margin=dict(t=40, b=20, l=20, r=20), showlegend=False)
        st.plotly_chart(fig_bar, use_container_width=True)

    with c_right:
        tot_days = sum(st_data["category_values"])
        rain_days = tot_days - st_data["category_values"][0]
        donut_df = pd.DataFrame({
            'Kategori': ['Hari Berhujan (≥0.1mm)', 'Hari Kering (0.0mm)'],
            'Jumlah': [rain_days, st_data["category_values"][0]]
        })
        fig_donut = px.pie(
            donut_df, names='Kategori', values='Jumlah', hole=0.55,
            title=f"Nisbah Hari Berhujan vs Kering ({curr_tgt_yr})",
            color_discrete_sequence=['#1f77b4', '#ffa500']
        )
        fig_donut.update_layout(height=420, margin=dict(t=40, b=20, l=20, r=20))
        st.plotly_chart(fig_donut, use_container_width=True)

    st.markdown("#### 🥧 Taburan Keamatan Hujan Harian")
    cat_df = pd.DataFrame({
        'Kategori': ["No Rain (0.0mm)", "Light (0.1–2.5mm)", "Moderate (2.6–10mm)", "Heavy (10.1–50mm)", "Very Heavy (>50mm)"],
        'Bilangan Hari': st_data["category_values"]
    })
    fig_cat = px.bar(cat_df, x='Kategori', y='Bilangan Hari', color='Kategori', text='Bilangan Hari')
    fig_cat.update_layout(height=320, showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig_cat, use_container_width=True)

# ------------------------------------------------------------
# TIER 2: ANALISIS SAINTIFIK
# ------------------------------------------------------------
with tab_scientific:
    sc1, sc2 = st.columns(2)
    
    with sc1:
        # Combined Target vs Mean Line
        fig_comp = go.Figure()
        fig_comp.add_trace(go.Bar(x=months, y=st_data["rainfall_target"].values, name=f"Hujan {curr_tgt_yr}", marker_color="#4682B4"))
        fig_comp.add_trace(go.Scatter(x=months, y=st_data["mean_monthly_total"].values, name=f"Normal ({YEAR_RANGE_TEXT})", line=dict(color="red", width=3)))
        fig_comp.update_layout(title=f"Perbandingan Hujan {curr_tgt_yr} vs Purata Normal", height=380, margin=dict(t=40, b=20, l=20, r=20))
        st.plotly_chart(fig_comp, use_container_width=True)

    with sc2:
        # Anomaly Diverging Bar
        anom_colors = ['#1f77b4' if v >= 0 else '#d62728' for v in st_data["anomaly_percent"].values]
        fig_anom = px.bar(x=months, y=st_data["anomaly_percent"].values, title=f"Anomali Hujan {curr_tgt_yr} (%)")
        fig_anom.update_traces(marker_color=anom_colors)
        fig_anom.add_hline(y=0, line_color="black", line_width=1)
        fig_anom.update_layout(height=380, margin=dict(t=40, b=20, l=20, r=20))
        st.plotly_chart(fig_anom, use_container_width=True)

    # 365-Day Daily Heatmap
    st.markdown(f"#### 🗺️ Matriks Kalendar Harian ({curr_tgt_yr})")
    tgt_df = st_data["data_df"][st_data["data_df"]["Year"] == curr_tgt_yr]
    piv_heat = tgt_df.pivot(index="Day", columns="Month", values="Rainfall").reindex(index=range(1, 32), columns=range(1, 13))
    piv_heat.columns = months
    fig_heat = px.imshow(piv_heat, labels=dict(x="Bulan", y="Hari", color="Hujan (mm)"), color_continuous_scale="Blues", aspect="auto")
    fig_heat.update_layout(height=450, margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig_heat, use_container_width=True)

    # Long-term Linear Regression Trend
    ann_totals = st_data["yearly_monthly_total"].sum(axis=1, min_count=10).dropna().reset_index()
    ann_totals.columns = ['Year', 'Rainfall']
    if len(ann_totals) > 1:
        z = np.polyfit(ann_totals['Year'], ann_totals['Rainfall'], 1)
        p = np.poly1d(z)
        ann_totals['Trend Line'] = p(ann_totals['Year'])
        fig_trend = px.line(
            ann_totals, x='Year', y=['Rainfall', 'Trend Line'], markers=True,
            title=f"Trend Jangka Panjang & Regresi Linear (m = {z[0]:.2f} mm/tahun)",
            color_discrete_map={'Rainfall': '#1f77b4', 'Trend Line': '#ff7f0e'}
        )
        fig_trend.update_layout(height=380, margin=dict(t=40, b=20, l=20, r=20))
        st.plotly_chart(fig_trend, use_container_width=True)

# ------------------------------------------------------------
# TIER 3: PERBANDINGAN MERENTAS STESEN
# ------------------------------------------------------------
with tab_multi:
    st.subheader("📈 Tindihan Profil Antara Stesen")
    all_st_names = sorted(list(station_results.keys()))
    sel_compare = st.multiselect("Pilih stesen:", all_st_names, default=all_st_names[:min(4, len(all_st_names))])
    
    if len(sel_compare) >= 2:
        fig_m = go.Figure()
        for s in sel_compare:
            s_mean = station_results[s]["mean_monthly_total"]
            fig_m.add_trace(go.Scatter(x=months, y=s_mean.values, mode='lines+markers', name=s))
        fig_m.update_layout(title=f"Perbandingan Purata Bulanan ({YEAR_RANGE_TEXT})", height=450, xaxis_title="Bulan", yaxis_title="Hujan (mm)")
        st.plotly_chart(fig_m, use_container_width=True)
    else:
        st.info("💡 Sila pilih sekurang-kurangnya 2 stesen di atas.")

# ------------------------------------------------------------
# TIER 4: JADUAL & MUAT TURUN
# ------------------------------------------------------------
with tab_data:
    st.subheader(f"📋 Ringkasan Statistik — {selected_station}")
    st.dataframe(st_data["analysis_table"], use_container_width=True)
    
    d1, d2 = st.columns(2)
    with d1:
        st.download_button(
            "📥 Muat Turun CSV Stesen Ini",
            st_data["analysis_table"].to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{selected_station}_Analisis_{YEAR_RANGE_TEXT}.csv",
            mime="text/csv"
        )
    with d2:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for s_name, res in station_results.items():
                zip_file.writestr(f"{s_name}/{s_name}_Statistical_Analysis.csv", res["analysis_table"].to_csv(index=False))
                zip_file.writestr(f"{s_name}/{s_name}_Monthly_Totals.csv", res["yearly_monthly_total"].to_csv())
        zip_buffer.seek(0)
        st.download_button(
            "📦 Muat Turun Pakej ZIP Semua Stesen",
            data=zip_buffer.getvalue(),
            file_name=f"Laporan_Klimatologi_Lengkap_{YEAR_RANGE_TEXT}.zip",
            mime="application/zip",
            type="primary"
        )

# ============================================================
# FOOTER
# ============================================================
st.divider()
st.caption("© 2026 Jabatan Meteorologi Malaysia (MetMalaysia) | Pejabat Meteorologi Sabah.")