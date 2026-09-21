"""
core/analyzer.py

Deterministic BESS Engineering Analyzer (Sections 27-33, 45-47).

This layer NEVER fabricates numbers. Every figure it reports comes from
re-running core.engine.compute_full_model on the base config and on a
modified clone, then diffing the two resulting year tables.

An optional external LLM/API can later be layered on top to turn these
structured diffs into prose (Section 27 intro) — this module is fully
useful without one.
"""

import pandas as pd
from core.engine import compute_full_model, apply_override

NUMERIC_COLUMNS_OF_INTEREST = [
    "DC Guarantee Capacity (MWh)",
    "POI Excl Aux - Discharge (MWh)",
    "POI Incl Aux - Discharge (MWh)",
    "Total AC MV Energy - Discharge (MWh)",
    "Charge Guarantee Excl Aux (MWh)",
    "Charge Guarantee Incl Aux (MWh)",
    "AC RTE Excl Aux (%)",
    "AC RTE Incl Aux (%)",
    "Requirement Margin (MWh)",
    "Requirement Margin (%)",
]


def run_scenario(base_config: dict, path: str, new_value):
    """Returns (modified_config, base_result, scenario_result, diff_table)."""
    base_result = compute_full_model(base_config)
    modified_config = apply_override(base_config, path, new_value)
    scenario_result = compute_full_model(modified_config)

    base_df = base_result["year_table"].set_index("Year")
    scen_df = scenario_result["year_table"].set_index("Year")

    diff_rows = []
    for year in base_df.index:
        row = {"Year": year}
        for col in NUMERIC_COLUMNS_OF_INTEREST:
            b = base_df.loc[year, col]
            s = scen_df.loc[year, col]
            if pd.isna(b) or pd.isna(s):
                row[f"{col} (Before)"] = b
                row[f"{col} (After)"] = s
                row[f"{col} (Delta)"] = None
                continue
            row[f"{col} (Before)"] = b
            row[f"{col} (After)"] = s
            row[f"{col} (Delta)"] = s - b
        b_status = base_df.loc[year, "Requirement Status"]
        s_status = scen_df.loc[year, "Requirement Status"]
        row["Requirement Status (Before)"] = b_status
        row["Requirement Status (After)"] = s_status
        row["Status Changed"] = b_status != s_status
        diff_rows.append(row)

    diff_table = pd.DataFrame(diff_rows)
    return modified_config, base_result, scenario_result, diff_table


def system_impact_summary(param_label: str, before_value, after_value, diff_table: pd.DataFrame) -> dict:
    """Section 29/45 — structured (not fabricated) system-impact summary."""
    flips = diff_table[diff_table["Status Changed"] == True]  # noqa: E712
    newly_not_matched = flips[flips["Requirement Status (After)"] == "NOT MATCHED"]
    newly_matched = flips[flips["Requirement Status (After)"] == "MATCHED"]

    avg_poi_delta = diff_table["POI Incl Aux - Discharge (MWh) (Delta)"].mean()
    avg_rte_delta = diff_table["AC RTE Incl Aux (%) (Delta)"].mean()

    return {
        "parameter": param_label,
        "before": before_value,
        "after": after_value,
        "years_flipped_to_not_matched": newly_not_matched["Year"].tolist(),
        "years_flipped_to_matched": newly_matched["Year"].tolist(),
        "avg_poi_incl_aux_delta_mwh": avg_poi_delta,
        "avg_ac_rte_incl_aux_delta_pct": avg_rte_delta,
        "direction": "decrease" if (isinstance(after_value, (int, float))
                                     and isinstance(before_value, (int, float))
                                     and after_value < before_value) else "change",
    }


def sensitivity_sweep(base_config: dict, path: str, values: list, target_year: str,
                       target_column: str = "POI Incl Aux - Discharge (MWh)") -> pd.DataFrame:
    """Section 31 — parameter sensitivity: sweep a single parameter across a
    list of candidate values and read off a target column for one year."""
    out = []
    for v in values:
        cfg = apply_override(base_config, path, v)
        result = compute_full_model(cfg)
        df = result["year_table"].set_index("Year")
        out.append({"Value": v, target_column: df.loc[target_year, target_column]})
    return pd.DataFrame(out)


def compare_scenarios(base_config: dict, scenarios: dict) -> pd.DataFrame:
    """Section 32 — side-by-side scenario comparison.
    `scenarios` = {"Case A - DOD reduced": [("years.__all__.dod", 90.0)], ...}
    Each scenario value is a list of (path, value) overrides applied in
    sequence on top of the base config.
    """
    rows = []
    base_result = compute_full_model(base_config)
    base_last_year = base_result["year_table"].iloc[-1]
    rows.append({
        "Scenario": "Base Case",
        "Installed DC Capacity (MWh)": base_result["installed_dc_capacity"],
        "Final-Year POI Incl Aux (MWh)": base_last_year["POI Incl Aux - Discharge (MWh)"],
        "Final-Year AC RTE Incl Aux (%)": base_last_year["AC RTE Incl Aux (%)"],
        "Final-Year Requirement Status": base_last_year["Requirement Status"],
    })
    for name, overrides in scenarios.items():
        cfg = base_config
        for path, value in overrides:
            cfg = apply_override(cfg, path, value)
        result = compute_full_model(cfg)
        last_year = result["year_table"].iloc[-1]
        rows.append({
            "Scenario": name,
            "Installed DC Capacity (MWh)": result["installed_dc_capacity"],
            "Final-Year POI Incl Aux (MWh)": last_year["POI Incl Aux - Discharge (MWh)"],
            "Final-Year AC RTE Incl Aux (%)": last_year["AC RTE Incl Aux (%)"],
            "Final-Year Requirement Status": last_year["Requirement Status"],
        })
    return pd.DataFrame(rows)
