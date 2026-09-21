"""
core/discharge.py

Section 7 (Normal Discharging - AC side), Section 8 (Discharge Time / C-rate),
Section 9 (Normal Discharge - POI).
"""

from core.units import pct, safe_div, flag_unit_ambiguity

AC_EFF_KEYS = [
    "lv_cable_eff", "pcs_eff", "pcs_idt_eff", "idt_eff",
    "dcdb_eff", "mv_eff", "transformer_eff", "kv11_eff", "measurement_acc",
]


def resolve_discharge_time(row: dict) -> dict:
    """Mode A: direct discharge time (h). Mode B: C-rate -> Discharge Time = 1/C-rate."""
    mode = row.get("time_mode", "time")
    if mode == "crate":
        c_rate = float(row.get("c_rate", 0) or 0)
        discharge_time = safe_div(1.0, c_rate)
        return {"mode": "crate", "c_rate": c_rate, "discharge_time": discharge_time}
    else:
        t = float(row.get("discharge_time", 0) or 0)
        c_rate = safe_div(1.0, t)
        return {"mode": "time", "c_rate": c_rate, "discharge_time": t}


def ac_efficiency_chain_factor(row: dict) -> float:
    factor = 1.0
    for key in AC_EFF_KEYS:
        factor *= pct(row.get(key, 100))
    return factor


def compute_aux_load_discharge(num_containers: float, aux_per_container_mw: float) -> float:
    """Aux Load Discharge (MW) = Initial Number of Containers x
    Auxiliary Consumption per Container - Discharge."""
    return float(num_containers) * float(aux_per_container_mw)


def compute_discharge_year(
    dc_guarantee_capacity_mwh: float,
    row: dict,
    num_containers: float,
    aux_per_container_discharge_mw: float,
    year_label: str = "",
    extra_aux_energy_mwh: float = 0.0,
) -> dict:
    """Full Section 9 chain for a single year.

    Returns poi_excl_aux, aux_load, discharge_time, aux_energy, poi_incl_aux
    plus traceability breadcrumbs.
    """
    time_info = resolve_discharge_time(row)
    discharge_time = time_info["discharge_time"]

    ac_factor = ac_efficiency_chain_factor(row)
    poi_excl_aux = dc_guarantee_capacity_mwh * ac_factor

    aux_load = compute_aux_load_discharge(num_containers, aux_per_container_discharge_mw)
    aux_energy = aux_load * discharge_time  # MW x h = MWh (dimensionally consistent)

    total_aux_energy = aux_energy + extra_aux_energy_mwh
    if extra_aux_energy_mwh:
        flag_unit_ambiguity(
            code="AUX_ADDITIVE_MIX",
            message=(
                "Additional auxiliary / standby energy (MWh, entered directly) is being "
                "summed with Aux Load (MW) x Discharge Time (h). Please verify the "
                "intended engineering interpretation."
            ),
            year=year_label,
        )

    poi_incl_aux = poi_excl_aux - total_aux_energy

    return {
        "discharge_time": discharge_time,
        "c_rate": time_info["c_rate"],
        "ac_efficiency_factor": ac_factor,
        "poi_excl_aux": poi_excl_aux,
        "aux_load_mw": aux_load,
        "aux_energy_mwh": aux_energy,
        "extra_aux_energy_mwh": extra_aux_energy_mwh,
        "total_aux_energy_mwh": total_aux_energy,
        "poi_incl_aux": poi_incl_aux,
        "formula_poi_excl": "DC Guarantee Capacity x (LV Cable x PCS x PCS-IDT x IDT x DCDB x MV x Transformer x 11kV x Measurement Acc)",
        "formula_poi_incl": "POI Excluding Aux - Auxiliary Energy",
    }
