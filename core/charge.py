"""
core/charge.py

Section 10 (Normal Charging), Section 11 (Charging Formulas),
Section 12 (DC-DC RTE).
"""

from core.units import pct, safe_div
from core.discharge import ac_efficiency_chain_factor, compute_aux_load_discharge


def charge_guarantee_capacity(
    dc_usable_energy_mwh: float,
    row: dict,
    dcdc_rte_pct: float,
) -> dict:
    """Section 11:

    Charge guarantee capacity excluding auxiliary =
        (Battery Nameplate Energy x Battery Qty x DOD x Discharge Eff
         x FAT-SAT Calendar Degradation x SOH)
        / (DC/AC Cable Eff x PCS Eff x Transformer Eff)
        / DC-DC RTE

    `dc_usable_energy_mwh` is passed in already carrying the
    (nameplate x qty x DOD x discharge_eff x calendar_deg x SOH) product —
    i.e. the same DC usable/guarantee energy computed in base_calculations,
    per the supplied methodology (this preserves the source formula's
    numerator exactly rather than re-deriving it a second way).

    The AC-side denominator uses the FULL efficiency chain the user
    supplied for charging (mirrors the discharge chain fields), consistent
    with Section 10's field list. DC-DC RTE is applied as its own
    independent, year-wise divisor per Section 12.
    """
    ac_factor = ac_efficiency_chain_factor(row)
    dcdc_rte = pct(dcdc_rte_pct)

    denom = ac_factor * dcdc_rte
    excl_aux = safe_div(dc_usable_energy_mwh, denom)

    return {
        "value_excl_aux": excl_aux,
        "ac_efficiency_factor": ac_factor,
        "dcdc_rte": dcdc_rte,
        "formula": "DC Usable Energy / (AC Efficiency Chain) / DC-DC RTE",
    }


def compute_charge_year(
    dc_usable_energy_mwh: float,
    row: dict,
    num_containers: float,
    aux_per_container_charge_mw: float,
    dcdc_rte_pct: float,
) -> dict:
    time_mode = row.get("time_mode", "time")
    if time_mode == "crate":
        c_rate = float(row.get("c_rate", 0) or 0)
        charge_time = safe_div(1.0, c_rate)
    else:
        charge_time = float(row.get("charge_time", row.get("discharge_time", 0)) or 0)

    cap = charge_guarantee_capacity(dc_usable_energy_mwh, row, dcdc_rte_pct)
    excl_aux = cap["value_excl_aux"]

    aux_load = compute_aux_load_discharge(num_containers, aux_per_container_charge_mw)
    incl_aux = excl_aux + aux_load * charge_time

    return {
        "charge_time": charge_time,
        "charge_guarantee_excl_aux": excl_aux,
        "charge_guarantee_incl_aux": incl_aux,
        "aux_load_mw": aux_load,
        "ac_efficiency_factor": cap["ac_efficiency_factor"],
        "dcdc_rte": cap["dcdc_rte"],
        "formula_excl": cap["formula"],
        "formula_incl": "Charge Guarantee Capacity Excl Aux + (Auxiliary Load x Charge Time)",
    }


def ac_rte(discharge_value: float, charge_value: float) -> float:
    """AC RTE = Discharge Guarantee Capacity / Charge Guarantee Capacity."""
    return safe_div(discharge_value, charge_value)
