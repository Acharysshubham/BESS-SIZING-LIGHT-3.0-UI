"""
core/validation.py

Implements the validation rules of Section 40 of the master spec.
Returns a list of (level, message) tuples — level is "error" or "warning".
Errors should block calculation of the affected year; warnings should not.
"""

from typing import List, Tuple

ValidationResult = List[Tuple[str, str]]


def _check_pct(name: str, value: float, results: ValidationResult, year_label: str = ""):
    tag = f"[{year_label}] " if year_label else ""
    if value is None:
        results.append(("error", f"{tag}{name} is missing."))
        return
    v = float(value)
    if v > 1.0:
        v = v  # already in percent form for this check
    else:
        v = v * 100.0
    if not (0 < v <= 100.0):
        results.append(("error", f"{tag}{name} must be > 0 and <= 100%. Got {v}."))


def validate_container_inputs(container_cfg: dict) -> ValidationResult:
    results: ValidationResult = []
    cap = container_cfg.get("dc_capacity_per_container", 0)
    n = container_cfg.get("num_containers", 0)
    if cap <= 0:
        results.append(("error", "DC installed capacity per container must be > 0."))
    if n <= 0:
        results.append(("error", "Initial number of containers must be > 0."))
    if float(n) != int(n):
        results.append(("error", "Container count must be an integer."))
    if container_cfg.get("aux_discharge_per_container_mw", 0) < 0:
        results.append(("error", "Auxiliary consumption (discharge) cannot be negative."))
    if container_cfg.get("aux_charge_per_container_mw", 0) < 0:
        results.append(("error", "Auxiliary consumption (charge) cannot be negative."))
    return results


def validate_timeline(timeline_cfg: dict) -> ValidationResult:
    results: ValidationResult = []
    if timeline_cfg.get("fat_required"):
        m = timeline_cfg.get("fat_months", 0)
        if m is None or m <= 0:
            results.append(("error", "FAT duration must be > 0 months when FAT is required."))
        elif m > 6:
            results.append(("error", "FAT duration cannot exceed 6 months."))
    if timeline_cfg.get("sat_required"):
        m = timeline_cfg.get("sat_months", 0)
        if m is None or m <= 0:
            results.append(("error", "SAT duration must be > 0 months when SAT is required."))
        elif m > 6:
            results.append(("error", "SAT duration cannot exceed 6 months."))
    if timeline_cfg.get("num_years", 0) < 1:
        results.append(("error", "Project must span at least 1 year."))
    return results


def validate_year_row(row: dict, year_label: str, kind: str) -> ValidationResult:
    """kind = 'discharge' or 'charge'"""
    results: ValidationResult = []
    pct_fields = [
        "availability", "eff" if False else None,
    ]
    for key in row:
        if key.endswith("_pct") or key in (
            "availability", "soh", "calendar_degradation", "dod",
            "lv_cable_eff", "pcs_eff", "pcs_idt_eff", "idt_eff", "dcdb_eff",
            "mv_eff", "transformer_eff", "kv11_eff", "measurement_acc",
            "dc_discharge_eff", "dc_charge_eff", "dcdc_rte",
        ):
            val = row.get(key)
            if val is None:
                continue
            v = val if val > 1 else val * 100.0
            if not (0 < v <= 100.0):
                results.append(("error", f"[{year_label}] {key} must be within (0, 100]%. Got {v}."))

    if kind == "discharge":
        mode = row.get("time_mode", "time")
        if mode == "crate":
            c = row.get("c_rate", 0)
            if c is None or c <= 0:
                results.append(("error", f"[{year_label}] C-rate must be > 0."))
        else:
            t = row.get("discharge_time", 0)
            if t is None or t <= 0:
                results.append(("error", f"[{year_label}] Discharge time must be > 0."))
    return results


def validate_augmentation_events(events: list, num_years: int) -> ValidationResult:
    results: ValidationResult = []
    seen_years = set()
    for ev in events:
        y = ev.get("year")
        q = ev.get("containers", 0)
        if y is None or y < 1 or y > num_years:
            results.append(("error", f"Augmentation year {y} is outside the project timeline."))
        if y in seen_years:
            results.append(("warning", f"Multiple augmentation events defined for Year {y}; "
                                        f"they will be summed."))
        seen_years.add(y)
        if q is None or q < 0:
            results.append(("error", f"Augmentation container quantity for Year {y} must be >= 0."))
    return results


def validate_requirement(value) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False
