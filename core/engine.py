"""
core/engine.py

Central orchestrator. Pure Python / pandas, independent of Streamlit.
Takes a project `config` dict and returns a dict of pandas DataFrames plus
metadata — this is the single source of truth consumed by the UI, the
Excel exporter, and the Engineering Analyzer.
"""

import copy
import pandas as pd

from core.units import reset_unit_warnings, UNIT_WARNING_LOG
from core.base_calculations import installed_dc_capacity, dc_guarantee_discharge_capacity
from core.discharge import compute_discharge_year
from core.charge import compute_charge_year
from core.auxiliary import total_extra_aux_energy_mwh
from core.augmentation import (
    augmented_capacity, augmented_energy_incl_aux, active_events_for_year,
    total_ac_mv_energy_discharge, total_ac_mv_energy_charge,
)
from core.rte import ac_rte_excl_aux, ac_rte_incl_aux
from core.requirements import match
from core.validation import validate_container_inputs, validate_timeline, validate_year_row


def default_year_row():
    return {
        "availability": 98.0,
        "dc_discharge_eff": 99.0,
        "dc_charge_eff": 99.0,
        "soh": 100.0,
        "calendar_degradation": 100.0,
        "dod": 95.0,
        "lv_cable_eff": 99.5,
        "pcs_eff": 98.5,
        "pcs_idt_eff": 99.5,
        "idt_eff": 99.0,
        "dcdb_eff": 99.5,
        "mv_eff": 99.3,
        "transformer_eff": 99.0,
        "kv11_eff": 99.5,
        "measurement_acc": 99.5,
        "time_mode": "time",
        "discharge_time": 4.0,
        "charge_time": 4.0,
        "c_rate": 0.25,
        "dcdc_rte": 97.0,
    }


def default_config():
    n_years = 15
    return {
        "container": {
            "dc_capacity_per_container": 2.2,
            "num_containers": 100,
            "aux_discharge_per_container_mw": 0.006,
            "aux_charge_per_container_mw": 0.006,
        },
        "timeline": {
            "fat_required": True, "fat_months": 2,
            "sat_required": True, "sat_months": 1,
            "num_years": n_years,
        },
        "years": {f"Year {y}": default_year_row() for y in range(1, n_years + 1)},
        "auxiliary": {
            "additional_aux_enabled": False, "additional_aux_value": 0.0,
            "standby_enabled": False, "standby_value": 0.0,
        },
        "augmentation": {
            "enabled": False,
            "events": [],
            "mismatch_losses": 99.0,
            "ac_mv_power_to_plant_mw": 0.0,
        },
        "requirements": {
            f"Year {y}": {"discharge_poi": None, "charge_poi": None}
            for y in range(1, n_years + 1)
        },
    }


def compute_full_model(config: dict) -> dict:
    """Runs the complete year-wise calculation chain and returns a dict:
        {
          "year_table": DataFrame,           # consolidated one-row-per-year table
          "discharge_detail": {year: {...}}, # traceability breadcrumbs
          "charge_detail": {year: {...}},
          "augmentation_detail": {year: {...}},
          "warnings": [...],
          "errors": [...],
        }
    """
    reset_unit_warnings()
    errors = []
    warnings = []

    errors += [m for lvl, m in validate_container_inputs(config["container"]) if lvl == "error"]
    warnings += [m for lvl, m in validate_container_inputs(config["container"]) if lvl == "warning"]
    errors += [m for lvl, m in validate_timeline(config["timeline"]) if lvl == "error"]

    container_cfg = config["container"]
    installed_cap = installed_dc_capacity(
        container_cfg["dc_capacity_per_container"], container_cfg["num_containers"]
    )

    years = list(config["years"].keys())
    rows = []
    discharge_detail = {}
    charge_detail = {}
    augmentation_detail = {}

    aug_cfg = config.get("augmentation", {"enabled": False, "events": []})
    aug_events = aug_cfg.get("events", []) if aug_cfg.get("enabled") else []
    aux_extra = total_extra_aux_energy_mwh(config.get("auxiliary", {}))

    cumulative_aug_containers = 0
    cumulative_aug_capacity = 0.0

    for idx, y_label in enumerate(years, start=1):
        row = config["years"][y_label]
        for lvl, m in validate_year_row(row, y_label, "discharge"):
            (errors if lvl == "error" else warnings).append(m)

        # --- DC side guarantee capacity (discharge) ---
        dc_gc = dc_guarantee_discharge_capacity(
            installed_cap, row["availability"], row["dc_discharge_eff"],
            row["soh"], row["calendar_degradation"], row["dod"],
        )

        # --- Discharge AC / POI ---
        disc = compute_discharge_year(
            dc_gc["value"], row, container_cfg["num_containers"],
            container_cfg["aux_discharge_per_container_mw"], y_label,
            extra_aux_energy_mwh=aux_extra["total_extra_mwh"],
        )
        discharge_detail[y_label] = {**dc_gc, **disc}

        # --- Charging (numerator reuses the DC discharge-side usable energy
        #     per the literal Section 11 formula, which specifies
        #     "Discharge Efficiency" inside the charging equation) ---
        chg = compute_charge_year(
            dc_gc["value"], row, container_cfg["num_containers"],
            container_cfg["aux_charge_per_container_mw"], row["dcdc_rte"],
        )
        charge_detail[y_label] = chg

        # --- RTE ---
        rte_excl = ac_rte_excl_aux(disc["poi_excl_aux"], chg["charge_guarantee_excl_aux"])
        rte_incl = ac_rte_incl_aux(disc["poi_incl_aux"], chg["charge_guarantee_incl_aux"])

        # --- Augmentation (if enabled) ---
        active = active_events_for_year(aug_events, idx)
        aug_events_energy = []
        aug_new_containers_this_year = sum(
            ev["containers"] for ev in aug_events if int(ev.get("year", 0)) == idx
        )
        cumulative_aug_containers += aug_new_containers_this_year

        for ev in active:
            cap = augmented_capacity(container_cfg["dc_capacity_per_container"], ev["containers"])
            res = augmented_energy_incl_aux(
                cap, row["dc_discharge_eff"], aug_cfg.get("mismatch_losses", 100.0),
                row["calendar_degradation"], row["soh"], row["dod"],
                row, container_cfg["aux_discharge_per_container_mw"],
                disc["discharge_time"], ev["containers"],
            )
            aug_events_energy.append(res["net_energy_incl_aux"])

        cumulative_aug_capacity = sum(
            augmented_capacity(container_cfg["dc_capacity_per_container"], ev["containers"])
            for ev in active
        )

        mv_result = total_ac_mv_energy_discharge(
            disc["poi_incl_aux"], aug_events_energy,
            aug_cfg.get("ac_mv_power_to_plant_mw", 0.0), disc["discharge_time"],
        )
        augmentation_detail[y_label] = {
            "active_events": active,
            "events_energy": aug_events_energy,
            "cumulative_containers": cumulative_aug_containers,
            "cumulative_capacity_mwh": cumulative_aug_capacity,
            "mv_result": mv_result,
        }

        total_discharge_energy = mv_result["total_ac_mv_energy"] if aug_cfg.get("enabled") else disc["poi_incl_aux"]

        req = config.get("requirements", {}).get(y_label, {})
        req_discharge = req.get("discharge_poi")
        match_result = match(total_discharge_energy, req_discharge) if req_discharge not in (None, "") else \
            {"status_bool": None, "status_label": "NO REQUIREMENT", "margin": None, "margin_pct": None}

        rows.append({
            "Year": y_label,
            "Containers": container_cfg["num_containers"] + cumulative_aug_containers,
            "Installed DC Capacity (MWh)": installed_cap,
            "Augmented Capacity (MWh)": cumulative_aug_capacity,
            "Availability (%)": row["availability"],
            "SOH (%)": row["soh"],
            "Calendar Degradation (%)": row["calendar_degradation"],
            "DOD (%)": row["dod"],
            "DC Guarantee Capacity (MWh)": dc_gc["value"],
            "Discharge Time (h)": disc["discharge_time"],
            "C-rate": disc["c_rate"],
            "POI Excl Aux - Discharge (MWh)": disc["poi_excl_aux"],
            "Aux Energy - Discharge (MWh)": disc["total_aux_energy_mwh"],
            "POI Incl Aux - Discharge (MWh)": disc["poi_incl_aux"],
            "Augmentation Energy (MWh)": sum(aug_events_energy),
            "Total AC MV Energy - Discharge (MWh)": total_discharge_energy,
            "Charge Time (h)": chg["charge_time"],
            "DC-DC RTE (%)": row["dcdc_rte"],
            "Charge Guarantee Excl Aux (MWh)": chg["charge_guarantee_excl_aux"],
            "Charge Guarantee Incl Aux (MWh)": chg["charge_guarantee_incl_aux"],
            "AC RTE Excl Aux (%)": rte_excl * 100.0,
            "AC RTE Incl Aux (%)": rte_incl * 100.0,
            "Required - Discharge POI (MWh)": req_discharge,
            "Requirement Status": match_result["status_label"],
            "Requirement Margin (MWh)": match_result["margin"],
            "Requirement Margin (%)": match_result["margin_pct"],
        })

    year_table = pd.DataFrame(rows)

    return {
        "installed_dc_capacity": installed_cap,
        "year_table": year_table,
        "discharge_detail": discharge_detail,
        "charge_detail": charge_detail,
        "augmentation_detail": augmentation_detail,
        "warnings": warnings + [w.message for w in UNIT_WARNING_LOG],
        "errors": errors,
    }


def clone_config(config: dict) -> dict:
    return copy.deepcopy(config)


def apply_override(config: dict, path: str, value) -> dict:
    """Applies a single scalar override into a cloned config, addressed by
    a simple dotted / bracket path such as:
        "years.Year 3.dod"
        "container.num_containers"
        "years.__all__.pcs_eff"   (applies to every year)
    Used by the What-If analyzer (Section 33).
    """
    cfg = clone_config(config)
    parts = path.split(".")
    if parts[0] == "years" and parts[1] == "__all__":
        field = parts[2]
        for y in cfg["years"]:
            cfg["years"][y][field] = value
        return cfg
    node = cfg
    for p in parts[:-1]:
        node = node[p]
    node[parts[-1]] = value
    return cfg
