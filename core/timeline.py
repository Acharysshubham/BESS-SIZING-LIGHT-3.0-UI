"""
core/timeline.py

Builds the project timeline: optional FAT, optional SAT, then Year 1..N.
No FAT/SAT calculation formulas are invented here — durations are pure
user inputs (Section 5). This module only orders the periods.
"""

from typing import List, Dict


def build_timeline(timeline_cfg: dict) -> List[Dict]:
    """Returns an ordered list of period descriptors:
    [{"label": "FAT", "type": "FAT", "months": 2}, {"label": "SAT", ...},
     {"label": "Year 1", "type": "YEAR", "index": 1}, ...]
    """
    periods = []
    if timeline_cfg.get("fat_required"):
        periods.append({
            "label": "FAT",
            "type": "FAT",
            "months": timeline_cfg.get("fat_months", 0),
        })
    if timeline_cfg.get("sat_required"):
        periods.append({
            "label": "SAT",
            "type": "SAT",
            "months": timeline_cfg.get("sat_months", 0),
        })
    num_years = int(timeline_cfg.get("num_years", 15))
    for y in range(1, num_years + 1):
        periods.append({"label": f"Year {y}", "type": "YEAR", "index": y})
    return periods


def year_labels(timeline_cfg: dict) -> List[str]:
    return [f"Year {y}" for y in range(1, int(timeline_cfg.get("num_years", 15)) + 1)]
