"""
core/augmentation.py

Sections 15-26 — Augmentation module for both discharge and charge sides.
"""

from core.units import pct, safe_div
from core.discharge import ac_efficiency_chain_factor, resolve_discharge_time


def augmented_capacity(dc_capacity_per_container: float, augmentation_containers: float) -> float:
    """Augmented Capacity = DC Installed Capacity per Container x
    Augmentation No. of Enclosures (Section 17/23)."""
    return float(dc_capacity_per_container) * float(augmentation_containers)


def augmented_dc_after_losses(
    augmented_capacity_mwh: float,
    dc_discharge_eff_pct: float,
    mismatch_losses_pct: float,
    calendar_degradation_pct: float,
    soh_pct: float,
    dod_pct: float,
) -> dict:
    """Section 18:

    Augmented DC Capacity After Losses =
        Augmented Capacity x DC Discharge Eff x Mismatch Losses
        x Calendar Degradation x SOH x DOD
    """
    factor = (
        pct(dc_discharge_eff_pct)
        * pct(mismatch_losses_pct)
        * pct(calendar_degradation_pct)
        * pct(soh_pct)
        * pct(dod_pct)
    )
    value = augmented_capacity_mwh * factor
    return {"value": value, "factor": factor}


def augmented_energy_incl_aux(
    augmented_capacity_mwh: float,
    dc_discharge_eff_pct: float,
    mismatch_losses_pct: float,
    calendar_degradation_pct: float,
    soh_pct: float,
    dod_pct: float,
    ac_row: dict,
    aux_per_container_mw: float,
    discharge_hours: float,
    augmentation_containers: float,
) -> dict:
    """Section 21 (Augmentation - Including Auxiliary), for a single
    augmentation event in a year where it is already active:

    (
      Augmented Capacity x DC Discharge Eff x Mismatch Losses x Calendar
      Degradation x SOH x DOD x [full AC efficiency chain]
    )
    -
    (
      Augmented Capacity for that Year x Auxiliary Consumption per
      Container x Discharge Hours
    )

    NOTE: the spec's subtracted term multiplies the *augmented capacity*
    (MWh) directly by an aux-consumption-per-container (MW) and discharge
    hours (h) — a term that is dimensionally a MWh^2/container-ish
    quantity unless "Auxiliary Consumption per Container" here is read as
    a per-container derate fraction rather than a MW figure. This is an
    engineering/unit ambiguity in the source formula (Section 39/53): we
    preserve it EXACTLY as supplied (using the augmentation event's own
    container count x per-container aux MW x hours, mirroring the base
    aux-energy pattern) rather than silently reinterpreting it.
    """
    dc_after_losses = augmented_dc_after_losses(
        augmented_capacity_mwh, dc_discharge_eff_pct, mismatch_losses_pct,
        calendar_degradation_pct, soh_pct, dod_pct,
    )
    ac_factor = ac_efficiency_chain_factor(ac_row)
    gross_ac = dc_after_losses["value"] * ac_factor

    aux_term = float(augmentation_containers) * float(aux_per_container_mw) * float(discharge_hours)

    net = gross_ac - aux_term
    return {
        "dc_after_losses": dc_after_losses["value"],
        "ac_factor": ac_factor,
        "gross_ac_energy": gross_ac,
        "aux_term": aux_term,
        "net_energy_incl_aux": net,
    }


def active_events_for_year(events: list, year_index: int) -> list:
    """All augmentation events whose start year is <= the given year
    (i.e. already commissioned by that year), summed if multiple share a
    year."""
    return [ev for ev in events if int(ev.get("year", 0)) <= year_index]


def total_ac_mv_energy_discharge(
    base_poi_incl_aux: float,
    augmented_events_energy: list,
    ac_mv_power_to_plant_mw: float,
    discharge_time_h: float,
) -> dict:
    """Section 22:

    Total AC MV Energy =
        Base Dischargeable Capacity at POI with Aux
        + Sum(Augmented Energy for all active events)
        - (AC MV Power to Plant Infrastructure x Discharge Time)
    """
    aug_sum = sum(augmented_events_energy) if augmented_events_energy else 0.0
    plant_draw = float(ac_mv_power_to_plant_mw) * float(discharge_time_h)
    total = base_poi_incl_aux + aug_sum - plant_draw
    return {
        "base_poi_incl_aux": base_poi_incl_aux,
        "augmentation_energy_sum": aug_sum,
        "plant_infrastructure_draw": plant_draw,
        "total_ac_mv_energy": total,
    }


def total_ac_mv_energy_charge(
    base_charge_incl_aux: float,
    augmented_events_energy: list,
    ac_mv_power_to_plant_mw: float,
    charge_time_h: float,
) -> dict:
    """Section 26 — mirrors Section 22 for the charging side. The spec
    states the plant-infrastructure term is ADDED for charging (energy
    drawn in addition to charging demand), using "the user's specified
    time relationship" — taken here as charge_time, preserving symmetry
    with the discharge-side treatment.
    """
    aug_sum = sum(augmented_events_energy) if augmented_events_energy else 0.0
    plant_draw = float(ac_mv_power_to_plant_mw) * float(charge_time_h)
    total = base_charge_incl_aux + aug_sum + plant_draw
    return {
        "base_charge_incl_aux": base_charge_incl_aux,
        "augmentation_energy_sum": aug_sum,
        "plant_infrastructure_draw": plant_draw,
        "total_ac_mv_energy": total,
    }
