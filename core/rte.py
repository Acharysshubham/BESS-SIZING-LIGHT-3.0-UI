"""
core/rte.py

Round-trip efficiency helpers. AC RTE (excl/incl aux) is:
    Discharge Guarantee Capacity / Charge Guarantee Capacity
DC-DC RTE is a direct, independently editable year-wise input (Section 12).
"""

from core.units import safe_div


def ac_rte_excl_aux(discharge_excl_aux: float, charge_excl_aux: float) -> float:
    return safe_div(discharge_excl_aux, charge_excl_aux)


def ac_rte_incl_aux(discharge_incl_aux: float, charge_incl_aux: float) -> float:
    return safe_div(discharge_incl_aux, charge_incl_aux)
