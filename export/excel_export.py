"""
export/excel_export.py

Generates a professional, auditable OpenPyXL workbook (Sections 43-44).
"""

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule

HEADER_FILL = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
INPUT_FILL = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
CALC_FILL = PatternFill(start_color="F3F4F6", end_color="F3F4F6", fill_type="solid")
GREEN_FILL = PatternFill(start_color="BBF7D0", end_color="BBF7D0", fill_type="solid")
RED_FILL = PatternFill(start_color="FECACA", end_color="FECACA", fill_type="solid")
TITLE_FONT = Font(bold=True, size=16, color="0F172A")
THIN = Side(style="thin", color="9CA3AF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _style_header_row(ws, row_idx, n_cols):
    for c in range(1, n_cols + 1):
        cell = ws.cell(row=row_idx, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER


def _autofit(ws, n_cols, min_width=12, max_width=42):
    for c in range(1, n_cols + 1):
        letter = get_column_letter(c)
        max_len = min_width
        for cell in ws[letter]:
            if cell.value is not None:
                max_len = max(max_len, len(str(cell.value)) + 2)
        ws.column_dimensions[letter].width = min(max_len, max_width)


def _write_dataframe(ws, df, start_row=1, title=None):
    row = start_row
    if title:
        ws.cell(row=row, column=1, value=title).font = TITLE_FONT
        row += 2
    header_row = row
    for c, col_name in enumerate(df.columns, start=1):
        ws.cell(row=header_row, column=c, value=col_name)
    _style_header_row(ws, header_row, len(df.columns))
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    for r, (_, data_row) in enumerate(df.iterrows(), start=header_row + 1):
        for c, col_name in enumerate(data_row.index, start=1):
            val = data_row[col_name]
            cell = ws.cell(row=r, column=c, value=val)
            cell.border = BORDER
            if "%" in str(col_name) and isinstance(val, (int, float)):
                cell.number_format = "0.00"
            elif "MWh" in str(col_name) and isinstance(val, (int, float)):
                cell.number_format = "#,##0.00"
    _autofit(ws, len(df.columns))
    return header_row, header_row + len(df)


def _apply_status_conditional_formatting(ws, col_letter, first_row, last_row):
    rng = f"{col_letter}{first_row}:{col_letter}{last_row}"
    ws.conditional_formatting.add(
        rng, CellIsRule(operator="equal", formula=['"MATCHED"'], fill=GREEN_FILL)
    )
    ws.conditional_formatting.add(
        rng, CellIsRule(operator="equal", formula=['"NOT MATCHED"'], fill=RED_FILL)
    )


def build_workbook(model_result: dict, config: dict, project_name: str = "BESS Project") -> Workbook:
    wb = Workbook()

    # --- Executive Summary ---
    ws = wb.active
    ws.title = "Executive Summary"
    ws["A1"] = f"{project_name} — BESS Sizing & Performance Summary"
    ws["A1"].font = TITLE_FONT
    ws["A3"] = "Installed DC Capacity (MWh)"
    ws["B3"] = model_result["installed_dc_capacity"]
    ws["A4"] = "Number of Years Modelled"
    ws["B4"] = len(model_result["year_table"])
    ws["A5"] = "Initial Number of Containers"
    ws["B5"] = config["container"]["num_containers"]
    ws["A6"] = "Augmentation Enabled"
    ws["B6"] = config.get("augmentation", {}).get("enabled", False)
    for r in range(3, 7):
        ws.cell(row=r, column=1).font = Font(bold=True)
    _autofit(ws, 2)

    # --- Initial Inputs ---
    ws2 = wb.create_sheet("Initial Inputs")
    ws2["A1"] = "Initial Inputs"
    ws2["A1"].font = TITLE_FONT
    r = 3
    for k, v in config["container"].items():
        ws2.cell(row=r, column=1, value=k).font = Font(bold=True)
        cell = ws2.cell(row=r, column=2, value=v)
        cell.fill = INPUT_FILL
        r += 1
    _autofit(ws2, 2)

    # --- Year-wise Base Calculation / Discharge / Charge / RTE / Requirement Matching ---
    year_table = model_result["year_table"]

    discharge_cols = [
        "Year", "Containers", "Installed DC Capacity (MWh)", "Availability (%)",
        "SOH (%)", "Calendar Degradation (%)", "DOD (%)", "DC Guarantee Capacity (MWh)",
        "Discharge Time (h)", "C-rate", "POI Excl Aux - Discharge (MWh)",
        "Aux Energy - Discharge (MWh)", "POI Incl Aux - Discharge (MWh)",
    ]
    ws3 = wb.create_sheet("Year-wise Base Calc")
    _write_dataframe(ws3, year_table[discharge_cols], title="Year-wise Base / Discharge Calculation")

    ws4 = wb.create_sheet("Discharging")
    _write_dataframe(ws4, year_table[discharge_cols], title="Discharging (DC + AC + POI)")

    charge_cols = ["Year", "Charge Time (h)", "DC-DC RTE (%)",
                   "Charge Guarantee Excl Aux (MWh)", "Charge Guarantee Incl Aux (MWh)"]
    ws5 = wb.create_sheet("Charging")
    _write_dataframe(ws5, year_table[charge_cols], title="Charging")

    ws6 = wb.create_sheet("Auxiliary Energy")
    aux_cfg = config.get("auxiliary", {})
    ws6["A1"] = "Auxiliary Energy Assumptions"
    ws6["A1"].font = TITLE_FONT
    r = 3
    for k, v in aux_cfg.items():
        ws6.cell(row=r, column=1, value=k).font = Font(bold=True)
        ws6.cell(row=r, column=2, value=v).fill = INPUT_FILL
        r += 1
    _write_dataframe(ws6, year_table[["Year", "Aux Energy - Discharge (MWh)"]], start_row=r + 2,
                      title="Year-wise Auxiliary Energy")

    ws7 = wb.create_sheet("Augmentation Schedule")
    events = config.get("augmentation", {}).get("events", [])
    import pandas as pd
    ev_df = pd.DataFrame(events) if events else pd.DataFrame(columns=["year", "containers"])
    _write_dataframe(ws7, ev_df, title="Augmentation Events")

    aug_cols = ["Year", "Augmented Capacity (MWh)", "Augmentation Energy (MWh)",
                "Total AC MV Energy - Discharge (MWh)"]
    ws8 = wb.create_sheet("Augmentation Discharge")
    _write_dataframe(ws8, year_table[aug_cols], title="Augmentation — Discharge Side")

    ws9 = wb.create_sheet("Augmentation Charge")
    ws9["A1"] = "Augmentation — Charge Side"
    ws9["A1"].font = TITLE_FONT
    ws9["A3"] = "See Charging sheet — augmentation charging mirrors the discharge-side structure per the supplied methodology."

    req_cols = ["Year", "Required - Discharge POI (MWh)", "Total AC MV Energy - Discharge (MWh)",
                "Requirement Status", "Requirement Margin (MWh)", "Requirement Margin (%)"]
    ws10 = wb.create_sheet("Requirement Matching")
    hdr_row, last_row = _write_dataframe(ws10, year_table[req_cols], title="Requirement Matching")
    status_col_idx = req_cols.index("Requirement Status") + 1
    status_letter = get_column_letter(status_col_idx)
    _apply_status_conditional_formatting(ws10, status_letter, hdr_row + 1, last_row)

    rte_cols = ["Year", "DC-DC RTE (%)", "AC RTE Excl Aux (%)", "AC RTE Incl Aux (%)"]
    ws11 = wb.create_sheet("RTE")
    _write_dataframe(ws11, year_table[rte_cols], title="Round-Trip Efficiency")

    ws12 = wb.create_sheet("Scenario Analysis")
    ws12["A1"] = "Scenario Analysis"
    ws12["A1"].font = TITLE_FONT
    ws12["A3"] = "Run scenarios in the What-If Analysis tab of the application, then export for a snapshot here."

    ws13 = wb.create_sheet("Engineering Analysis")
    ws13["A1"] = "Engineering Analysis / Warnings"
    ws13["A1"].font = TITLE_FONT
    r = 3
    for w in model_result.get("warnings", []):
        ws13.cell(row=r, column=1, value=f"WARNING: {w}")
        r += 1
    if not model_result.get("warnings"):
        ws13.cell(row=r, column=1, value="No engineering unit-check warnings raised.")

    return wb
