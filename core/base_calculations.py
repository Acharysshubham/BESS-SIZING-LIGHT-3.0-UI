"""
core/base_calculations.py

Section 4 (Initial Inputs) and Section 6 (Normal Discharging - DC Side).
"""

from core.units import pct


def installed_dc_capacity(dc_capacity_per_container: float, num_containers: float) -> float:
    """Installed DC Capacity (MWh) = DC installed capacity per container x
    Initial number of containers."""
    return float(dc_capacity_per_container) * float(num_containers)


def dc_guarantee_discharge_capacity(
    installed_capacity_mwh: float,
    availability_pct: float,
    dc_discharge_eff_pct: float,
    soh_pct: float,
    calendar_degradation_pct: float,
    dod_pct: float,
) -> dict:
    """Guarantee Discharge Capacity at DC Side (Section 6):

    Installed DC Capacity x BESS Availability x DC Discharging Efficiency
        x SOH x Calendar Degradation x DOD

    All percentage parameters are converted to decimal factors internally.
    Returns the value plus the individual decimal factors used, for
    traceability (Section 34/54).
    """
    availability = pct(availability_pct)
    dc_eff = pct(dc_discharge_eff_pct)
    soh = pct(soh_pct)
    cal_deg = pct(calendar_degradation_pct)
    dod = pct(dod_pct)

    value = (
        installed_capacity_mwh
        * availability
        * dc_eff
        * soh
        * cal_deg
        * dod
    )
    return {
        "value": value,
        "factors": {
            "installed_capacity_mwh": installed_capacity_mwh,
            "availability": availability,
            "dc_discharge_eff": dc_eff,
            "soh": soh,
            "calendar_degradation": cal_deg,
            "dod": dod,
        },
        "formula": "Installed DC Capacity x Availability x DC Discharge Eff x SOH x Calendar Degradation x DOD",
    }
