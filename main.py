from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
import pandas as pd
import numpy as np
import io
import os
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from typing import Optional

app = FastAPI(title="MetClimate Sabah Climatology API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

@app.get("/")
async def read_index():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"message": "index.html tidak dijumpai"}

def parse_full_aaws_file(file_bytes: bytes, filename: str):
    engine = "xlrd" if filename.endswith(".xls") else "openpyxl"
    try:
        xls = pd.ExcelFile(io.BytesIO(file_bytes), engine=engine)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gagal membaca fail Excel: {str(e)}")

    stations = {}

    for sheet_name in xls.sheet_names:
        if sheet_name.lower() in ["datalist", "list", "index", "sheet1_copy"]:
            continue

        try:
            df_raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, engine=engine)
        except Exception:
            continue

        if len(df_raw) < 5:
            continue

        station_name = sheet_name
        for idx in range(min(10, len(df_raw))):
            row_str = " ".join([str(x) for x in df_raw.iloc[idx].values])
            if "station" in row_str.lower():
                val = df_raw.iloc[idx, 1] if pd.notna(df_raw.iloc[idx, 1]) else df_raw.iloc[idx, 0]
                station_name = str(val).replace("Station:", "").replace("Station", "").replace(":", "").strip()
                break

        header_row = None
        for idx in range(min(20, len(df_raw))):
            row_vals = [str(x).strip().lower() for x in df_raw.iloc[idx].values]
            if "year" in row_vals and "month" in row_vals and "day" in row_vals:
                header_row = idx
                break

        if header_row is not None:
            data_df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, skiprows=header_row + 1, engine=engine)
            data_df = data_df.iloc[:, 0:4]
            data_df.columns = ["Year", "Month", "Day", "Rainfall"]

            data_df["Year"] = pd.to_numeric(data_df["Year"], errors="coerce")
            data_df["Month"] = pd.to_numeric(data_df["Month"], errors="coerce")
            data_df["Day"] = pd.to_numeric(data_df["Day"], errors="coerce")
            data_df = data_df.dropna(subset=["Year", "Month", "Day"])
            data_df["Year"] = data_df["Year"].astype(int)
            data_df["Month"] = data_df["Month"].astype(int)
            data_df["Day"] = data_df["Day"].astype(int)

            data_df["Rainfall"] = data_df["Rainfall"].astype(str).str.strip().str.upper()
            data_df["Rainfall"] = data_df["Rainfall"].replace({"TR": "0.1", "TRACE": "0.1", "NONE": "0.0", "NULL": "nan", "-": "nan"})
            data_df["Rainfall"] = pd.to_numeric(data_df["Rainfall"], errors="coerce")
            data_df.loc[data_df["Rainfall"] < 0, "Rainfall"] = np.nan

            years = sorted(data_df["Year"].unique().tolist())
            if years:
                stations[station_name] = {
                    "sheet": sheet_name,
                    "data": data_df,
                    "years": years
                }

    if not stations:
        raise HTTPException(status_code=400, detail="Format lajur Year, Month, Day, Rainfall tidak ditemui.")

    return stations


def write_single_sheet_borang(ws, station_name: str, year: int, df_station: pd.DataFrame, wet_th: float = 0.1):
    """Menulis format rasmi Borang Kosong ke dalam satu worksheet openpyxl."""
    target_df = df_station[df_station["Year"] == year]

    matrix_dict = {}
    monthly_totals = []
    rain_days = []
    highest_falls = []
    highest_dates = []

    for m in range(1, 13):
        m_df = target_df[target_df["Month"] == m]
        m_sum = m_df["Rainfall"].sum() if not m_df.empty else 0.0
        monthly_totals.append(round(float(m_sum), 1) if pd.notna(m_sum) else 0.0)
        rain_days.append(int((m_df["Rainfall"] >= wet_th).sum()) if not m_df.empty else 0)

        if not m_df.empty and m_df["Rainfall"].notna().any():
            max_v = m_df["Rainfall"].max()
            if pd.notna(max_v) and max_v > 0:
                highest_falls.append(round(float(max_v), 1))
                top_days = m_df[m_df["Rainfall"] == max_v]["Day"].tolist()
                highest_dates.append(",".join([str(d) for d in top_days]))
            else:
                highest_falls.append(0.0)
                highest_dates.append("-")
        else:
            highest_falls.append(0.0)
            highest_dates.append("-")

    for d in range(1, 32):
        matrix_dict[d] = []
        for m in range(1, 13):
            val = target_df[(target_df["Month"] == m) & (target_df["Day"] == d)]["Rainfall"].values
            if len(val) > 0 and pd.notna(val[0]):
                matrix_dict[d].append(round(float(val[0]), 1))
            else:
                matrix_dict[d].append(None)

    font_title = Font(name="Arial", size=10, bold=True)
    font_header = Font(name="Arial", size=9, bold=True)
    font_data = Font(name="Arial", size=9)
    font_bold = Font(name="Arial", size=9, bold=True)

    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    thin = Side(border_style="thin", color="000000")
    grid_border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.merge_cells("A1:M1")
    ws["A1"] = "JABATAN METEOROLOGI MALAYSIA"
    ws["A1"].font = font_title
    ws["A1"].alignment = align_center

    ws.merge_cells("A2:M2")
    ws["A2"] = "DAILY RAINFALL RECORD IN MILLIMETRES"
    ws["A2"].font = font_title
    ws["A2"].alignment = align_center

    ws.merge_cells("A4:H4")
    ws["A4"] = f"STATION  :  {station_name.upper()}"
    ws["A4"].font = font_bold
    ws["A4"].alignment = align_left

    ws.merge_cells("J4:M4")
    ws["J4"] = f"YEAR :  {year}"
    ws["J4"].font = font_bold
    ws["J4"].alignment = align_right

    headers = ["DATE", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=6, column=col_idx, value=h)
        cell.font = font_header
        cell.alignment = align_center
        cell.border = grid_border
        cell.fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")

    for day in range(1, 32):
        r = 6 + day
        d_cell = ws.cell(row=r, column=1, value=day)
        d_cell.font = font_header
        d_cell.alignment = align_center
        d_cell.border = grid_border

        day_vals = matrix_dict.get(day, [None] * 12)
        for m_idx in range(12):
            val = day_vals[m_idx]
            val_display = val if (val is not None and pd.notna(val)) else ""
            c = ws.cell(row=r, column=m_idx + 2, value=val_display)
            c.font = font_data
            c.alignment = align_center
            c.border = grid_border

    c_tot = ws.cell(row=38, column=1, value="TOTAL")
    c_tot.font = font_bold
    c_tot.alignment = align_center
    c_tot.border = grid_border
    for m_idx in range(12):
        c = ws.cell(row=38, column=m_idx + 2, value=monthly_totals[m_idx])
        c.font = font_bold
        c.alignment = align_center
        c.border = grid_border

    c_nod = ws.cell(row=39, column=1, value="No.Of days")
    c_nod.font = font_bold
    c_nod.alignment = align_center
    c_nod.border = grid_border
    for m_idx in range(12):
        c = ws.cell(row=39, column=m_idx + 2, value=rain_days[m_idx])
        c.font = font_bold
        c.alignment = align_center
        c.border = grid_border

    c_hf = ws.cell(row=40, column=1, value="Highest fall")
    c_hf.font = font_bold
    c_hf.alignment = align_center
    c_hf.border = grid_border
    for m_idx in range(12):
        c = ws.cell(row=40, column=m_idx + 2, value=highest_falls[m_idx])
        c.font = font_bold
        c.alignment = align_center
        c.border = grid_border

    c_dt = ws.cell(row=41, column=1, value="Date")
    c_dt.font = font_bold
    c_dt.alignment = align_center
    c_dt.border = grid_border
    for m_idx in range(12):
        c = ws.cell(row=41, column=m_idx + 2, value=highest_dates[m_idx])
        c.font = font_bold
        c.alignment = align_center
        c.border = grid_border

    ws.merge_cells("A43:D43")
    ws["A43"] = "P.K.0497(Litho)"
    ws["A43"].font = Font(name="Arial", size=8, italic=True)

    ws.merge_cells("I43:M43")
    ws["I43"] = "TR: Amount less than 0.1mm"
    ws["I43"].font = Font(name="Arial", size=8, italic=True)
    ws["I43"].alignment = align_right

    ws.column_dimensions['A'].width = 14
    for col_letter in ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M']:
        ws.column_dimensions[col_letter].width = 8


@app.post("/api/process-aaws")
async def process_aaws(
    file: UploadFile = File(...),
    selected_station: Optional[str] = Form(None),
    target_year: Optional[int] = Form(None),
    max_missing: int = Form(10),
    max_consec: int = Form(4),
    wet_th: float = Form(0.1),
    suspect_th: float = Form(150.0),
    extreme_th: float = Form(250.0)
):
    contents = await file.read()
    stations_dict = parse_full_aaws_file(contents, file.filename)
    station_names = list(stations_dict.keys())

    if selected_station not in stations_dict:
        selected_station = station_names[0]

    st_info = stations_dict[selected_station]
    df = st_info["data"]
    available_years = st_info["years"]

    if target_year is None or target_year not in available_years:
        target_year = available_years[-1]

    qc_logs = {"suspect": [], "extreme": [], "rejected_months": []}

    for _, r in df[df["Rainfall"] > suspect_th].iterrows():
        qc_logs["suspect"].append({
            "date": f"{int(r['Year'])}-{int(r['Month']):02d}-{int(r['Day']):02d}",
            "value": float(r["Rainfall"]),
            "action": "Flagged (> Suspect Limit)"
        })

    for _, r in df[df["Rainfall"] > extreme_th].iterrows():
        qc_logs["extreme"].append({
            "date": f"{int(r['Year'])}-{int(r['Month']):02d}-{int(r['Day']):02d}",
            "value": float(r["Rainfall"]),
            "action": "Flagged (> Extreme Limit)"
        })

    monthly_data_by_year = {}
    for yr in available_years:
        yr_df = df[df["Year"] == yr]
        month_sums = []
        wet_days_counts = []

        for m in range(1, 13):
            m_df = yr_df[yr_df["Month"] == m]
            missing_count = m_df["Rainfall"].isna().sum()

            is_na = m_df["Rainfall"].isna().astype(int)
            consec_missing = is_na.groupby((~is_na.astype(bool)).cumsum()).sum().max() if not m_df.empty else 31

            if missing_count > max_missing or consec_missing > max_consec or m_df.empty:
                month_sums.append(np.nan)
                wet_days_counts.append(0)
                if yr == target_year:
                    qc_logs["rejected_months"].append(f"{MONTH_NAMES[m-1]} {yr}")
            else:
                month_sums.append(float(m_df["Rainfall"].sum()))
                wet_days_counts.append(int((m_df["Rainfall"] >= wet_th).sum()))

        monthly_data_by_year[yr] = {"totals": month_sums, "wet_days": wet_days_counts}

    all_totals_matrix = np.array([v["totals"] for v in monthly_data_by_year.values()])
    normal_mean = np.nanmean(all_totals_matrix, axis=0)
    normal_mean = np.where(np.isnan(normal_mean), 0, normal_mean).round(1).tolist()

    target_monthly_totals = [0 if np.isnan(v) else round(v, 1) for v in monthly_data_by_year[target_year]["totals"]]
    target_wet_days = monthly_data_by_year[target_year]["wet_days"]

    annual_totals = []
    annual_wet_days = []
    rx1day_list = []

    for yr in available_years:
        yr_df = df[df["Year"] == yr]
        annual_totals.append(round(float(yr_df["Rainfall"].sum()), 1))
        annual_wet_days.append(int((yr_df["Rainfall"] >= wet_th).sum()))
        rx1 = yr_df["Rainfall"].max()
        rx1day_list.append(round(float(rx1), 1) if pd.notna(rx1) else 0.0)

    x = np.arange(len(available_years))
    if len(x) > 1:
        slope, intercept = np.polyfit(x, annual_totals, 1)
        trend_line = [round(float(slope * xi + intercept), 1) for xi in x]
    else:
        trend_line = annual_totals

    target_df = df[df["Year"] == target_year]
    borang_matrix = {}
    highest_falls = []
    highest_dates = []

    for m in range(1, 13):
        m_df = target_df[target_df["Month"] == m]
        if not m_df.empty and m_df["Rainfall"].notna().any():
            max_val = m_df["Rainfall"].max()
            if pd.notna(max_val) and max_val > 0:
                highest_falls.append(round(float(max_val), 1))
                top_days = m_df[m_df["Rainfall"] == max_val]["Day"].tolist()
                highest_dates.append(",".join([str(d) for d in top_days]))
            else:
                highest_falls.append(0.0)
                highest_dates.append("-")
        else:
            highest_falls.append(0.0)
            highest_dates.append("-")

    for d in range(1, 32):
        borang_matrix[d] = []
        for m in range(1, 13):
            val = target_df[(target_df["Month"] == m) & (target_df["Day"] == d)]["Rainfall"].values
            if len(val) > 0 and pd.notna(val[0]):
                borang_matrix[d].append(round(float(val[0]), 1))
            else:
                borang_matrix[d].append(None)

    annual_mean_norm = round(float(np.sum(normal_mean)), 1)
    peak_idx = int(np.argmax(target_monthly_totals)) if any(target_monthly_totals) else 0
    dry_idx = int(np.argmin(target_monthly_totals)) if any(target_monthly_totals) else 0

    return {
        "station_list": station_names,
        "selected_station": selected_station,
        "available_years": available_years,
        "selected_year": target_year,
        "kpi": {
            "annual_mean": annual_mean_norm,
            "peak_month": f"{MONTH_NAMES[peak_idx]} ({target_monthly_totals[peak_idx]} mm)",
            "dry_month": f"{MONTH_NAMES[dry_idx]} ({target_monthly_totals[dry_idx]} mm)",
            "qc_valid_percent": f"{max(0, 100 - len(qc_logs['rejected_months'])*8)}%"
        },
        "monthly": {
            "target_totals": target_monthly_totals,
            "normal_mean": normal_mean,
            "wet_days": target_wet_days
        },
        "annual": {
            "years": available_years,
            "totals": annual_totals,
            "trend_line": trend_line,
            "wet_days": annual_wet_days,
            "rx1day": rx1day_list
        },
        "qc_logs": qc_logs,
        "borang_kosong_format": {
            "matrix": borang_matrix,
            "monthly_totals": target_monthly_totals,
            "rain_days_count": target_wet_days,
            "highest_falls": highest_falls,
            "highest_dates": highest_dates
        }
    }


@app.post("/api/export-borang-excel")
async def export_borang_excel(
    file: UploadFile = File(...),
    selected_station: str = Form(...),
    target_year: Optional[int] = Form(None),
    all_years: bool = Form(False),
    wet_th: float = Form(0.1)
):
    """Menjana fail Borang Kosong sama ada 1 tahun sahaja atau SEMUA TAHUN dalam multi-tabs."""
    contents = await file.read()
    stations_dict = parse_full_aaws_file(contents, file.filename)

    if selected_station not in stations_dict:
        selected_station = list(stations_dict.keys())[0]

    st_data = stations_dict[selected_station]
    df = st_data["data"]
    years = st_data["years"]

    wb = openpyxl.Workbook()
    # Buang sheet asal
    wb.remove(wb.active)

    if all_years:
        # Loop semua tahun yang ada dalam dataset stesen
        for yr in years:
            ws = wb.create_sheet(title=str(yr))
            write_single_sheet_borang(ws, selected_station, yr, df, wet_th)
        filename_out = f"Borang_Kosong_ALL_YEARS_{selected_station.replace(' ', '_')}_{years[0]}-{years[-1]}.xlsx"
    else:
        yr = target_year if target_year in years else years[-1]
        ws = wb.create_sheet(title=str(yr))
        write_single_sheet_borang(ws, selected_station, yr, df, wet_th)
        filename_out = f"Borang_Kosong_{selected_station.replace(' ', '_')}_{yr}.xlsx"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename_out}"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)