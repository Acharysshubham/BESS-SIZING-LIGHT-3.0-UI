"""
core/units.py

Strict unit handling helpers.

Conventions used throughout the engine:
    MW   -> Power
    MWh  -> Energy
    h    -> Time (hours)
    %    -> stored as entered (e.g. 95.0) at the UI boundary, converted to a
             decimal factor (0.95) the instant it enters a calculation.
    C    -> C-rate (dimensionless, 1/h)
    Nos. -> integer container/unit count

This module NEVER changes a supplied formula. It only performs the
mechanical percent -> decimal conversion and flags places where the
source methodology mixes power (MW) and energy (MWh) terms, per the
master spec (Section 39, "Units").
"""

from dataclasses import dataclass, field


def pct(value: float) -> float:
    """Convert a percentage expressed as e.g. 95.0 into a decimal factor 0.95.

    If a caller already passed a decimal (0 <= value <= 1) it is returned
    unchanged, since some UI widgets store sliders natively as 0-1.
    """
    if value is None:
        return 0.0
    v = float(value)
    if v > 1.0:
        return v / 100.0
    return v


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Division that never raises — returns `default` (and lets the caller
    flag a warning) instead of propagating a ZeroDivisionError / inf / nan
    silently through the workbook.
    """
    try:
        if denominator == 0 or denominator is None:
            return default
        result = numerator / denominator
        if result != result:  # NaN check
            return default
        return result
    except (TypeError, ZeroDivisionError):
        return default


@dataclass
class UnitWarning:
    code: str
    message: str
    year: str = ""


UNIT_WARNING_LOG = []


def flag_unit_ambiguity(code: str, message: str, year: str = "") -> UnitWarning:
    """Register (and return) a non-fatal engineering unit-check warning.

    Per Section 39/53 of the spec: the software must NEVER silently
    'fix' a formula that mixes MW and MWh (e.g. Aux Load (MW) x
    Discharge Time (h) subtracted directly from an MWh POI figure).
    Instead it preserves the supplied methodology and raises a visible
    warning so the engineer can confirm intent.
    """
    w = UnitWarning(code=code, message=message, year=year)
    UNIT_WARNING_LOG.append(w)
    return w


def reset_unit_warnings():
    UNIT_WARNING_LOG.clear()
