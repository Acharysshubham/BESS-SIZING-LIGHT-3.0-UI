"""
core/requirements.py

Section 14 (Requirement Matching) and Section 38 (Requirement Margin).
"""

from core.units import safe_div


def match(calculated: float, required: float) -> dict:
    """Calculated >= Required -> MATCHED/TRUE, else NOT MATCHED/FALSE.

    Also computes the absolute and percentage margin (Section 38) for
    engineering visibility. Margin never replaces the boolean matching
    logic — it is additional context only.
    """
    if required is None:
        return {
            "status_bool": None, "status_label": "NO REQUIREMENT",
            "margin": None, "margin_pct": None,
        }
    matched = calculated >= required
    margin = calculated - required
    margin_pct = safe_div(margin, required) * 100.0 if required else None
    return {
        "status_bool": matched,
        "status_label": "MATCHED" if matched else "NOT MATCHED",
        "margin": margin,
        "margin_pct": margin_pct,
    }
