import streamlit as st
import pandas as pd
import numpy as np
import io
import zipfile
import calendar
import plotly.express as px
import plotly.graph_objects as go

# =========================================================
# 1. KONFIGURASI HALAMAN
# =========================================================
st.set_page_config(
    page_title="Sistem Bersepadu Analisis Klimatologi | MetMalaysia Sabah",
    layout="wide",
    page_icon="🌤️"
)

# =========================================================
# 2. KAMUS BAHASA (BILINGUAL DICTIONARY)
# =========================================================
TEXTS = {
    "BM": {
        "title": "Sistem Integrasi Analisis & Klimatologi AAWS",
        "subtitle": "Jabatan Meteorologi Malaysia (MetMalaysia) | Pejabat Meteorologi Sabah",
        "nav_analysis": "📊 Analisis Parameter",
        "nav_qc": "📋 Semakan Kualiti & WMO Audit",
        "sidebar_header": "📁 Kawalan & Tetapan Data",
        "manual_header": "📖 Panduan Operasi & Standard WMO",
        "manual_desc": """
        **Panduan Penggunaan Sistem Bersepadu:**
        1. **Muat Naik Fail:** Masukkan satu atau lebih fail AAWS (`.xls` / `.xlsx`) di bar sisi.
        2. **Mod Analisis:** Pilih antara Pandangan Awam (Public), Saintifik Lanjutan (Scientific), atau Perbandingan Rentas Stesen.
        3. **Audit WMO & QC:** Sistem menyaring data hilang dan menandakan rekod mencurigakan (*Suspect >150mm*) dan melampau (*Extreme >250mm*).
        4. **Eksport Laporan:** Muat turun borang matriks piawai Excel, graf HTML interaktif, atau arkib ZIP lengkap.
        """,
        "upload_label": "Muat naik fail siri masa AAWS (.xls / .xlsx):",
        "qc_mode_label": "⚙️ Piawaian Data Hilang (WMO):",
        "download_zip": "📦 Muat Turun Semua Laporan ({param}) [.ZIP]",
        "zip_filename": "Laporan_Klimatologi_Bersepadu_{param}.zip",
        "select_param": "Parameter Cerapan:",
        "param_rain": "🌧️ Hujan (Rainfall)",
        "param_temp": "🌡️ Suhu Udara (Temperature)",
        "select_station": "Pilih Stesen Cerapan:",
        "station_name": "Stesen Cerapan",
        "record_period": "Tempoh Rekod",
        "completeness_rate": "Skor Kelengkapan WMO",
        "invalid_months": "Bulan Tidak Lengkap",
        "view_public": "🌐 Pandangan Umum (Public Dashboard)",
        "view_scientific": "🔬 Pandangan Saintifik (Scientific Analysis)",
        "view_matrix": "📋 Borang Matriks Piawai (Sheets)",
        "view_compare": "📊 Perbandingan Merentas Stesen",
        "qc_title": "Log Audit Integriti Data (WMO-No. 1203 & QC Thresholds)",
        "qc_filter_failed": "🔍 Tapis: Tunjuk data bermasalah/hilang sahaja",
        "download_qc_csv": "📥 Muat Turun Log Audit (.CSV)",
        "info_upload": "👈 Sila muat naik fail raw AAWS di menu bar sisi kiri untuk memulakan analisis."
    },
    "EN": {
        "title": "Integrated AAWS Climatology & Analysis System",
        "subtitle": "Malaysian Meteorological Department (MetMalaysia) | Sabah Meteorological Office",
        "nav_analysis": "📊 Parameter Analytics",
        "nav_qc": "📋 Quality Control & WMO Audit",
        "sidebar_header": "📁 Data Controls & Settings",
        "manual_header": "📖 User Manual & Standards",
        "manual_desc": """
        **Integrated System Guide:**
        1. **Upload Data:** Upload raw AAWS time-series files (`.xls` / `.xlsx`) via the sidebar.
        2. **Analytical Views:** Switch smoothly between Public Dashboard, Advanced Scientific Analytics, or Multi-Station Comparison.
        3. **WMO & QC Screening:** Automated missing data screening with suspect (>150mm) & extreme (>250mm) flaggers.
        4. **Export Reports:** Download official Excel matrix sheets, interactive HTML plots, or bulk ZIP packages.
        """,
        "upload_label": "Upload AAWS time-series files (.xls / .xlsx):",
        "qc_mode_label": "⚙️ Missing Data Standard (WMO):",
        "download_zip": "📦 Download All Reports ({param}) [.ZIP]",
        "zip_filename": "Integrated_Climatology_Report_{param}.zip",
        "select_param": "Observation Parameter:",
        "param_rain": "🌧️ Rainfall",
        "param_temp": "🌡️ Air Temperature",
        "select_station": "Select Observation Station:",
        "station_name": "Station Name",
        "record_period": "Record Period",
        "completeness_rate": "WMO Completeness Score",
        "invalid_months": "Incomplete Months",
        "view_public": "🌐 Public Dashboard",
        "view_scientific": "🔬 Scientific Analysis",
        "view_matrix": "📋 Standard Excel Matrix",
        "view_compare": "📊 Multi-Station Comparison",
        "qc_title": "Data Integrity Audit Log (WMO-No. 1203 & QC)",
        "qc_filter_failed": "🔍 Filter: Show missing/flagged records only",
        "download_qc_csv": "📥 Download Audit Log (.CSV)",
        "info_upload": "👈 Please upload raw AAWS files via the sidebar to start analysis."
    }
}

month_names_en = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']

# =========================================================
# 3. SIDEBAR & TETAPAN KAWALAN
# =========================================================
with st.sidebar:
    selected_lang = st.selectbox("🌐 Bahasa / Language", options=["Bahasa Melayu", "English"])
    lang_key = "BM" if selected_lang == "Bahasa Melayu" else "EN"
    t = TEXTS[lang_key]

    with st.expander(t["manual_header"], expanded=False):
        st.markdown(t["manual_desc"])

    st.divider()
    st.markdown(f"### {t['sidebar_header']}")

    qc_rule = st.radio(
        t["qc_mode_label"],
        options=["WMO Standard (11/5 Rule)", "Strict Rule (5/3 Rule)", "No Filter (Raw Data)"],
        index=0
    )

    st.markdown("---")
    st.markdown("#### 🌧️ Had Ambang QC (Thresholds)")
    WET_DAY_THRES = st.number_input("Had Hari Berhujan (mm)", value=0.1, step=0.05)
    SUSPECT_THRES = st.number_input("Had Hujan Suspect (mm)", value=150.0, step=10.0)
    EXTREME_THRES = st.number_input("Had Hujan Ekstrem (mm)", value=250.0, step=10.0)

    st.markdown("---")
    uploaded_files = st.file_uploader(
        t["upload_label"],
        type=["xls", "xlsx"],
        accept_multiple_files=True
    )

# =========================================================
# 4. PENGEPALA APLIKASI
# =========================================================
header_col1, header_col2 = st.columns([1, 7])
with header_col1:
    st.markdown("<h1 style='font-size: 55px; margin: 0;'>🌤️</h1>", unsafe_allow_html=True)
with header_col2:
    st.markdown(f"### **{t['title']}**")
    st.caption(f"🏛️ {t['subtitle']} | Standard WMO-No. 1203")

st.divider()

# =========================================================
# 5. ENJIN PEMPROSESAN DATA & QC
# =========================================================
def clean_station_name(val):
    val = str(val).replace(":", "").strip()
    return val.lstrip(': -_').upper() if val else "UNKNOWN_STATION"

def detect_parameter(header_text):
    text_lower = header_text.lower()
    if any(k in text_lower for k in ['temp', 'suhu', 'celsius', '°c']):
        return "Temperature"
    return "Rainfall"

def process_aaws_files(files):
    all_data = {"Rainfall": {}, "Temperature": {}}
    for file in files:
        try:
            xls = pd.ExcelFile(file)
            for sheet in xls.sheet_names:
                if str(sheet).lower().strip() in ['datalist', 'info', 'summary']:
                    continue
                df_raw = pd.read_excel(xls, sheet_name=sheet, header=None)
                header_dump = " ".join([str(val) for val in df_raw.iloc[:12, :].values.flatten()])
                param_type = detect_parameter(header_dump)
                
                # Cari baris data bermula
                start_row = 11
                for r in range(min(15, len(df_raw))):
                    row_txt = " ".join([str(x).lower() for x in df_raw.iloc[r].tolist() if pd.notna(x)])
                    if ("year" in row_txt or "tahun" in row_txt) and ("month" in row_txt or "bulan" in row_txt):
                        start_row = r + 1
                        break
                        
                st_name = ""
                for r in range(min(8, len(df_raw))):
                    for c in range(min(6, len(df_raw.columns))):
                        cell_str = str(df_raw.iloc[r, c]).strip()
                        if any(k in cell_str.lower() for k in ['station', 'stesen']):
                            if ':' in cell_str and len(cell_str.split(':', 1)[1].strip()) > 1:
                                st_name = cell_str.split(':', 1)[1].strip()
                            elif c + 1 < len(df_raw.columns) and pd.notna(df_raw.iloc[r, c + 1]):
                                st_name = str(df_raw.iloc[r, c + 1]).strip()
                                
                if not st_name:
                    st_name = str(sheet).strip()
                st_name = clean_station_name(st_name)
                
                data = df_raw.iloc[start_row:].copy().iloc[:, :4]
                data.columns = ['Year', 'Month', 'Day', 'Value']
                
                data['Value'] = data['Value'].astype(str).str.strip().str.upper()
                data['Value'] = data['Value'].replace(['TR', 'TRACE'], '0.1')
                
                data['Year'] = pd.to_numeric(data['Year'], errors='coerce')
                data['Month'] = pd.to_numeric(data['Month'], errors='coerce')
                data['Day'] = pd.to_numeric(data['Day'], errors='coerce')
                data['Value_Numeric'] = pd.to_numeric(data['Value'], errors='coerce')
                data['Value_Display'] = data['Value']
                
                data = data.dropna(subset=['Year', 'Month', 'Day'])
                data = data[(data['Year'] >= 1900) & (data['Year'] <= 2100)]
                data['Year'] = data['Year'].astype(int)
                data['Month'] = data['Month'].astype(int)
                data['Day'] = data['Day'].astype(int)
                
                if not data.empty:
                    target_dict = all_data[param_type]
                    if st_name in target_dict:
                        comb = pd.concat([target_dict[st_name], data], ignore_index=True)
                        target_dict[st_name] = comb.drop_duplicates(subset=['Year', 'Month', 'Day'])
                    else:
                        target_dict[st_name] = data
        except Exception as e:
            st.error(f"Ralat memproses {file.name}: {e}")
    return all_data

def evaluate_qc(series, rule):
    missing = series.isna().sum()
    is_na = series.isna().astype(int)
    blocks = (is_na != is_na.shift()).cumsum()
    consec = is_na.groupby(blocks).transform('sum') * is_na
    max_consec = consec.max() if not consec.empty else 0
    
    if rule == "WMO Standard (11/5 Rule)":
        is_valid = not (missing >= 11 or max_consec >= 5)
    elif rule == "Strict Rule (5/3 Rule)":
        is_valid = not (missing > 5 or max_consec > 3)
    else:
        is_valid = True
    return is_valid, missing, max_consec

def generate_qc_table(df_stesen, rule):
    records = []
    for yr in sorted(df_stesen['Year'].unique()):
        df_yr = df_stesen[df_stesen['Year'] == yr]
        pivot = df_yr.pivot(index='Day', columns='Month', values='Value_Numeric').reindex(index=range(1, 32), columns=range(1, 13))
        for m in range(1, 13):
            col = pivot[m]
            is_valid, miss, consec = evaluate_qc(col, rule)
            records.append({
                'Year': yr,
                'Month': m,
                'Month_Name': month_names_en[m-1],
                'Missing_Days': miss,
                'Max_Consecutive_Missing': consec,
                'Is_Valid_WMO': is_valid
            })
    return pd.DataFrame(records)

def generate_station_excel(df_stesen, st_name, rule, param_mode):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for yr in sorted(df_stesen['Year'].unique()):
            df_yr = df_stesen[df_stesen['Year'] == yr]
            pivot_num = df_yr.pivot(index='Day', columns='Month', values='Value_Numeric').reindex(index=range(1, 32), columns=range(1, 13))
            pivot_dsp = df_yr.pivot(index='Day', columns='Month', values='Value_Display').reindex(index=range(1, 32), columns=range(1, 13))
            
            s1, s2, s3, s4 = [], [], [], []
            for m in range(1, 13):
                col = pivot_num[m]
                is_valid, _, _ = evaluate_qc(col, rule)
                if is_valid and col.notna().any():
                    if param_mode == "Rainfall":
                        tot = col.sum(skipna=True)
                        s1.append(round(tot, 1) if pd.notna(tot) else "N.A")
                        s2.append(int((col >= 0.1).sum()))
                        max_v = col.max(skipna=True)
                        s3.append(round(max_v, 1) if pd.notna(max_v) else "N.A")
                        try:
                            s4.append(int(col.idxmax(skipna=True)))
                        except Exception:
                            s4.append("-")
                    else:
                        s1.append(round(col.mean(skipna=True), 1))
                        s2.append(round(col.max(skipna=True), 1))
                        s3.append(round(col.min(skipna=True), 1))
                        s4.append(round(col.max() - col.min(), 1) if pd.notna(col.max()) else "-")
                else:
                    s1.append("N.A (Incomplete)")
                    s2.append("N.A")
                    s3.append("N.A")
                    s4.append("-")
                    
            rep = pivot_dsp.copy()
            if param_mode == "Rainfall":
                rep.loc['TOTAL (mm)'] = s1
                rep.loc['No. Of Days (>=0.1mm)'] = s2
                rep.loc['Highest Fall (mm)'] = s3
                rep.loc['Date of Highest'] = s4
            else:
                rep.loc['MEAN TEMP (°C)'] = s1
                rep.loc['MAX TEMP (°C)'] = s2
                rep.loc['MIN TEMP (°C)'] = s3
                rep.loc['TEMP RANGE (°C)'] = s4
                
            rep.columns = month_names_en
            rep.index.name = "DATE"
            rep.to_excel(writer, sheet_name=str(yr)[:31])
    output.seek(0)
    return output

all_data = process_aaws_files(uploaded_files) if uploaded_files else {"Rainfall": {}, "Temperature": {}}

# =========================================================
# 6. NAVIGASI TAB UTAMA
# =========================================================
tab_main_analysis, tab_wmo_qc = st.tabs([t["nav_analysis"], t["nav_qc"]])

# =========================================================
# TAB 1: ANALISIS PARAMETER
# =========================================================
with tab_main_analysis:
    if uploaded_files:
        col_c1, col_c2, col_c3 = st.columns([1.5, 2, 1.5])
        with col_c1:
            chosen_p = st.radio(t["select_param"], [t["param_rain"], t["param_temp"]], horizontal=True)
            param_mode = "Rainfall" if chosen_p == t["param_rain"] else "Temperature"
            unit = "mm" if param_mode == "Rainfall" else "°C"
            
        st_dict = all_data.get(param_mode, {})
        if not st_dict:
            st.warning("⚠️ Tiada data untuk parameter ini dikesan dalam fail yang dimuat naik.")
        else:
            with col_c2:
                selected_st = st.selectbox(t["select_station"], list(st_dict.keys()))
            with col_c3:
                st.write("")
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for s_name, s_df in st_dict.items():
                        x_bytes = generate_station_excel(s_df, s_name, qc_rule, param_mode)
                        zf.writestr(f"{param_mode}_{s_name}.xlsx", x_bytes.getvalue())
                zip_buf.seek(0)
                st.download_button(
                    t["download_zip"].format(param=param_mode),
                    zip_buf,
                    file_name=t["zip_filename"].format(param=param_mode),
                    mime="application/zip",
                    type="primary",
                    use_container_width=True
                )
                
            df_curr = st_dict[selected_st]
            qc_df = generate_qc_table(df_curr, qc_rule)
            
            # Pengiraan Kelengkapan WMO
            valid_m_cnt = qc_df['Is_Valid_WMO'].sum()
            total_m_cnt = len(qc_df)
            wmo_score = (valid_m_cnt / total_m_cnt) * 100 if total_m_cnt > 0 else 0
            
            # Semakan Suspect & Extreme
            suspect_records = df_curr[df_curr['Value_Numeric'] > SUSPECT_THRES]
            extreme_records = df_curr[df_curr['Value_Numeric'] > EXTREME_THRES]
            
            # KPI Hero Cards
            with st.container(border=True):
                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric(t["station_name"], selected_st)
                k2.metric(t["record_period"], f"{df_curr['Year'].min()}–{df_curr['Year'].max()}")
                k3.metric(t["completeness_rate"], f"{wmo_score:.1f}%")
                k4.metric("Suspect (>150mm)", f"{len(suspect_records)} Rekod")
                k5.metric("Extreme (>250mm)", f"{len(extreme_records)} Rekod")
                
            # 4 Mod Paparan Utama
            sub_tabs = st.tabs([
                t["view_public"],
                t["view_scientific"],
                t["view_compare"],
                t["view_matrix"]
            ])
            
            # -------------------------------------------------
            # 1. PANDANGAN AWAM (PUBLIC DASHBOARD)
            # -------------------------------------------------
            with sub_tabs[0]:
                st.subheader(f"🌐 Dashboard Awam — Stesen {selected_st}")
                
                # Agregat Bulanan (Hanya Bulan Sah WMO)
                m_totals = df_curr.groupby(['Year', 'Month'])['Value_Numeric'].sum(min_count=1).reset_index()
                m_totals = m_totals.merge(qc_df, on=['Year', 'Month'])
                m_valid = m_totals[m_totals['Is_Valid_WMO'] == True]
                
                summary_pub = m_valid.groupby('Month')['Value_Numeric'].agg(['mean', 'max', 'min']).reset_index()
                summary_pub['Bulan'] = summary_pub['Month'].apply(lambda x: month_names_en[x-1])
                
                wettest = summary_pub.loc[summary_pub['mean'].idxmax()]
                driest = summary_pub.loc[summary_pub['mean'].idxmin()]
                
                p_c1, p_c2, p_c3, p_c4 = st.columns(4)
                p_c1.metric("Purata Hujan Tahunan Normal", f"{summary_pub['mean'].sum():.1f} {unit}")
                p_c2.metric("Bulan Paling Basah", f"{wettest['Bulan']} ({wettest['mean']:.1f} {unit})")
                p_c3.metric("Bulan Paling Kering", f"{driest['Bulan']} ({driest['mean']:.1f} {unit})")
                p_c4.metric("Rekod Harian Tertinggi", f"{df_curr['Value_Numeric'].max():.1f} {unit}")
                
                col_p_left, col_p_right = st.columns([6, 4])
                with col_p_left:
                    st.markdown("### 🌧️ Purata Penerimaan Hujan Bulanan Normal")
                    fig_pub = px.bar(
                        summary_pub, x='Bulan', y='mean', text='mean',
                        labels={'mean': f'Purata ({unit})', 'Bulan': 'Bulan'},
                        color='mean', color_continuous_scale='Blues'
                    )
                    fig_pub.update_traces(texttemplate='%{text:.1f} ' + unit, textposition='outside')
                    st.plotly_chart(fig_pub, use_container_width=True)
                    
                with col_p_right:
                    st.markdown("### ☀️ Nisbah Hari Berhujan vs Hari Kering")
                    rainy = (df_curr['Value_Numeric'] >= WET_DAY_THRES).sum()
                    dry = (df_curr['Value_Numeric'] < WET_DAY_THRES).sum()
                    donut_df = pd.DataFrame({
                        'Kategori': [f'Hari Berhujan (≥{WET_DAY_THRES}mm)', 'Hari Kering (0.0mm)'],
                        'Jumlah': [rainy, dry]
                    })
                    fig_pie = px.pie(donut_df, names='Kategori', values='Jumlah', hole=0.5, color_discrete_sequence=['#1f77b4', '#ffa500'])
                    st.plotly_chart(fig_pie, use_container_width=True)
                    
                # Carta Kategori Hujan
                st.markdown("### 🥧 Taburan Mengikut Kategori Keamatan Hujan (MetMalaysia)")
                r_vals = df_curr['Value_Numeric'].dropna()
                cat_df = pd.DataFrame({
                    'Kategori': ['Tiada Hujan (0.0mm)', 'Hujan Ringan (0.1–2.5mm)', 'Hujan Sederhana (2.6–10.0mm)', 'Hujan Lebat (10.1–50.0mm)', 'Hujan Sangat Lebat (>50mm)'],
                    'Bilangan Hari': [
                        (r_vals == 0).sum(),
                        ((r_vals >= 0.1) & (r_vals <= 2.5)).sum(),
                        ((r_vals > 2.5) & (r_vals <= 10.0)).sum(),
                        ((r_vals > 10.0) & (r_vals <= 50.0)).sum(),
                        (r_vals > 50.0).sum()
                    ]
                })
                fig_cat = px.bar(cat_df, x='Kategori', y='Bilangan Hari', color='Kategori', text='Bilangan Hari')
                st.plotly_chart(fig_cat, use_container_width=True)

            # -------------------------------------------------
            # 2. PANDANGAN SAINTIFIK (SCIENTIFIC ANALYSIS)
            # -------------------------------------------------
            with sub_tabs[1]:
                st.subheader(f"🔬 Analisis Iklim Saintifik — Stesen {selected_st}")
                
                # 1. Profil Normal & Ribbon Julat Min-Maks
                st.markdown("#### 1. Profil Purata Bulanan & Julat Sejarah Ekstrem (Range Envelope)")
                m_stats = df_curr.groupby('Month')['Value_Numeric'].agg(['mean', 'min', 'max']).reset_index()
                m_stats['Bulan'] = m_stats['Month'].apply(lambda x: month_names_en[x-1])
                
                fig_ribbon = go.Figure()
                fig_ribbon.add_trace(go.Scatter(x=m_stats['Bulan'], y=m_stats['max'], mode='lines', line=dict(width=0), showlegend=False))
                fig_ribbon.add_trace(go.Scatter(
                    x=m_stats['Bulan'], y=m_stats['min'], mode='lines', line=dict(width=0), fill='tonexty',
                    fillcolor='rgba(31, 119, 180, 0.2)', name='Julat Ekstrem (Min-Max)'
                ))
                fig_ribbon.add_trace(go.Scatter(
                    x=m_stats['Bulan'], y=m_stats['mean'], mode='lines+markers', name=f'Purata Normal ({param_mode})',
                    line=dict(color='#1f77b4', width=3), marker=dict(size=8)
                ))
                fig_ribbon.update_layout(xaxis_title="Bulan", yaxis_title=f"{param_mode} ({unit})")
                st.plotly_chart(fig_ribbon, use_container_width=True)
                
                # 2. Boxplot Taburan Hujan Bulanan
                st.markdown("#### 2. Boxplot Taburan Hujan Bulanan (Variabiliti & Outliers)")
                df_curr['Month_Name'] = df_curr['Month'].apply(lambda x: month_names_en[x-1])
                fig_box = px.box(
                    df_curr[df_curr['Value_Numeric'] >= WET_DAY_THRES], x='Month_Name', y='Value_Numeric',
                    color='Month_Name', points="outliers", labels={'Value_Numeric': f'Hujan Harian ({unit})', 'Month_Name': 'Bulan'}
                )
                st.plotly_chart(fig_box, use_container_width=True)
                
                # 3. Trend Siri Masa & Regresi Linear
                st.markdown("#### 3. Trend Siri Masa Tahunan & Kecerunan Regresi Linear")
                ann_df = df_curr.groupby('Year')['Value_Numeric'].agg('sum' if param_mode == "Rainfall" else 'mean').reset_index()
                if len(ann_df) > 1:
                    z = np.polyfit(ann_df['Year'], ann_df['Value_Numeric'], 1)
                    p = np.poly1d(z)
                    ann_df['Trend_Line'] = p(ann_df['Year'])
                    fig_tr = px.line(
                        ann_df, x='Year', y=['Value_Numeric', 'Trend_Line'], markers=True,
                        title=f"Kecerunan Trend: m = {z[0]:.2f} {unit}/tahun",
                        labels={'value': f'{param_mode} ({unit})', 'Year': 'Tahun', 'variable': 'Penunjuk'},
                        color_discrete_map={'Value_Numeric': '#1f77b4', 'Trend_Line': '#ff7f0e'}
                    )
                    st.plotly_chart(fig_tr, use_container_width=True)
                    
                # 4. Anomali Iklim
                st.markdown("#### 4. Anomali Siri Masa Iklim (Climate Anomaly)")
                b_mean = ann_df['Value_Numeric'].mean()
                ann_df['Anomaly'] = ann_df['Value_Numeric'] - b_mean
                ann_df['Kategori'] = np.where(ann_df['Anomaly'] >= 0, 'Lebih Normal (Wet)', 'Kurang Normal (Dry)')
                fig_anom = px.bar(
                    ann_df, x='Year', y='Anomaly', color='Kategori',
                    color_discrete_map={'Lebih Normal (Wet)': '#1f77b4', 'Kurang Normal (Dry)': '#d62728'}
                )
                fig_anom.add_hline(y=0, line_color="black")
                st.plotly_chart(fig_anom, use_container_width=True)

                # 5. Matriks Harian (Heatmap)
                st.markdown("#### 5. Matriks Harian (Heatmap 365 Hari)")
                chosen_heat_yr = st.selectbox("Pilih Tahun Heatmap:", sorted(df_curr['Year'].unique()), index=len(df_curr['Year'].unique())-1)
                df_h = df_curr[df_curr['Year'] == chosen_heat_yr]
                piv_h = df_h.pivot(index='Day', columns='Month', values='Value_Numeric').reindex(index=range(1, 32), columns=range(1, 13))
                fig_h = px.imshow(
                    piv_h, labels=dict(x="Bulan", y="Hari", color=f"{param_mode} ({unit})"),
                    x=month_names_en, y=[str(d) for d in range(1, 32)], color_continuous_scale="Blues", aspect="auto"
                )
                st.plotly_chart(fig_h, use_container_width=True)

            # -------------------------------------------------
            # 3. PERBANDINGAN MERENTAS STESEN
            # -------------------------------------------------
            with sub_tabs[2]:
                st.subheader("📊 Perbandingan Bertindih Merentas Stesen")
                all_st_list = list(st_dict.keys())
                sel_st = st.multiselect("Pilih stesen-stesen untuk perbandingan:", all_st_list, default=all_st_list[:min(3, len(all_st_list))])
                
                if len(sel_st) >= 2:
                    fig_mc = go.Figure()
                    for s_name in sel_st:
                        d_st = st_dict[s_name]
                        st_m = d_st.groupby('Month')['Value_Numeric'].mean().reset_index()
                        st_m['Bulan'] = st_m['Month'].apply(lambda x: month_names_en[x-1])
                        fig_mc.add_trace(go.Scatter(x=st_m['Bulan'], y=st_m['Value_Numeric'], mode='lines+markers', name=s_name))
                    fig_mc.update_layout(xaxis_title="Bulan", yaxis_title=f"Purata {param_mode} ({unit})")
                    st.plotly_chart(fig_mc, use_container_width=True)
                else:
                    st.info("💡 Sila pilih sekurang-kurangnya 2 stesen di atas.")

            # -------------------------------------------------
            # 4. BORANG MATRIKS STANDARD
            # -------------------------------------------------
            with sub_tabs[3]:
                st.subheader(f"📋 Borang Rekod Arkib Piawai — Stesen {selected_st}")
                s_excel = generate_station_excel(df_curr, selected_st, qc_rule, param_mode)
                st.download_button(
                    f"📥 Muat Turun Fail Excel ({selected_st})",
                    s_excel,
                    file_name=f"Borang_{param_mode}_{selected_st}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.dataframe(df_curr.head(25), use_container_width=True)
    else:
        st.info(t["info_upload"])

# =========================================================
# TAB 2: AUDIT WMO & KAWALAN KUALITI (QC)
# =========================================================
with tab_wmo_qc:
    st.subheader(t["qc_title"])
    if uploaded_files:
        qc_p_choice = st.radio(t["select_param"], [t["param_rain"], t["param_temp"]], horizontal=True, key="qc_radio_tab")
        p_mode_qc = "Rainfall" if qc_p_choice == t["param_rain"] else "Temperature"
        st_dict_qc = all_data.get(p_mode_qc, {})
        
        if st_dict_qc:
            qc_st_choice = st.selectbox(t["select_station"], list(st_dict_qc.keys()), key="qc_st_select")
            df_st_qc = st_dict_qc[qc_st_choice]
            qc_tbl = generate_qc_table(df_st_qc, qc_rule)
            
            # Semakan Suspect & Extreme
            suspects = df_st_qc[df_st_qc['Value_Numeric'] > SUSPECT_THRES]
            extremes = df_st_qc[df_st_qc['Value_Numeric'] > EXTREME_THRES]
            
            qc_sub1, qc_sub2, qc_sub3 = st.tabs(["📅 Audit WMO Bulanan", "⚠️ Rekod Suspect (>150mm)", "🚨 Rekod Ekstrem (>250mm)"])
            
            with qc_sub1:
                filter_failed = st.checkbox(t["qc_filter_failed"], value=False)
                disp_qc = qc_tbl[qc_tbl['Missing_Days'] > 0] if filter_failed else qc_tbl
                st.dataframe(disp_qc, use_container_width=True)
                st.download_button(t["download_qc_csv"], disp_qc.to_csv(index=False).encode('utf-8'), f"WMO_Audit_{qc_st_choice}.csv", "text/csv")
                
            with qc_sub2:
                st.write(f"Jumlah Rekod Suspect: **{len(suspects)}**")
                if not suspects.empty:
                    st.dataframe(suspects[['Year', 'Month', 'Day', 'Value_Numeric']], use_container_width=True)
                else:
                    st.success("Tiada rekod suspect dikesan.")
                    
            with qc_sub3:
                st.write(f"Jumlah Rekod Ekstrem: **{len(extremes)}**")
                if not extremes.empty:
                    st.dataframe(extremes[['Year', 'Month', 'Day', 'Value_Numeric']], use_container_width=True)
                else:
                    st.success("Tiada rekod ekstrem dikesan.")
    else:
        st.info(t["info_upload"])

# =========================================================
# FOOTER
# =========================================================
st.divider()
st.caption("© 2026 Jabatan Meteorologi Malaysia (MetMalaysia) | Pejabat Meteorologi Sabah. Standard WMO-No. 1203 Certified.")