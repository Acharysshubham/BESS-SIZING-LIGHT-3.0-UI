import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from core.base_calculations import installed_dc_capacity, dc_guarantee_discharge_capacity
from core.discharge import resolve_discharge_time, ac_efficiency_chain_factor, compute_discharge_year
from core.charge import charge_guarantee_capacity, ac_rte
from core.auxiliary import container_auxiliary_load, resolve_additional_auxiliary, resolve_standby_energy
from core.requirements import match
from core.augmentation import augmented_capacity, augmented_dc_after_losses
from core.engine import default_config, compute_full_model
from core.analyzer import run_scenario


def test_installed_dc_capacity():
    assert installed_dc_capacity(2.2, 100) == pytest.approx(220.0)


def test_dc_guarantee_discharge_capacity():
    res = dc_guarantee_discharge_capacity(220.0, 98.0, 99.0, 100.0, 100.0, 95.0)
    expected = 220.0 * 0.98 * 0.99 * 1.0 * 1.0 * 0.95
    assert res["value"] == pytest.approx(expected)


def test_discharge_time_from_crate():
    info = resolve_discharge_time({"time_mode": "crate", "c_rate": 0.25})
    assert info["discharge_time"] == pytest.approx(4.0)


def test_discharge_time_direct():
    info = resolve_discharge_time({"time_mode": "time", "discharge_time": 2.0})
    assert info["discharge_time"] == pytest.approx(2.0)
    assert info["c_rate"] == pytest.approx(0.5)


def test_ac_efficiency_chain_factor_all_100_is_one():
    row = {k: 100.0 for k in [
        "lv_cable_eff", "pcs_eff", "pcs_idt_eff", "idt_eff", "dcdb_eff",
        "mv_eff", "transformer_eff", "kv11_eff", "measurement_acc",
    ]}
    assert ac_efficiency_chain_factor(row) == pytest.approx(1.0)


def test_requirement_matching_true():
    r = match(215.0, 210.0)
    assert r["status_bool"] is True
    assert r["status_label"] == "MATCHED"
    assert r["margin"] == pytest.approx(5.0)


def test_requirement_matching_false():
    r = match(200.0, 205.0)
    assert r["status_bool"] is False
    assert r["status_label"] == "NOT MATCHED"
    assert r["margin"] == pytest.approx(-5.0)


def test_auxiliary_container_load():
    assert container_auxiliary_load(100, 0.006) == pytest.approx(0.6)


def test_additional_aux_disabled_is_zero():
    assert resolve_additional_auxiliary({"additional_aux_enabled": False, "additional_aux_value": 5}) == 0.0


def test_standby_enabled_uses_value():
    assert resolve_standby_energy({"standby_enabled": True, "standby_value": 3.5}) == 3.5


def test_augmented_capacity():
    assert augmented_capacity(2.2, 10) == pytest.approx(22.0)


def test_augmented_dc_after_losses():
    res = augmented_dc_after_losses(22.0, 99.0, 99.0, 100.0, 100.0, 95.0)
    expected = 22.0 * 0.99 * 0.99 * 1.0 * 1.0 * 0.95
    assert res["value"] == pytest.approx(expected)


def test_ac_rte_basic():
    assert ac_rte(190.0, 200.0) == pytest.approx(0.95)


def test_default_config_runs_end_to_end():
    cfg = default_config()
    result = compute_full_model(cfg)
    assert result["errors"] == []
    assert len(result["year_table"]) == cfg["timeline"]["num_years"]
    assert result["installed_dc_capacity"] == pytest.approx(220.0)


def test_analyzer_dod_reduction_reduces_poi():
    cfg = default_config()
    _, base_result, scenario_result, diff = run_scenario(cfg, "years.__all__.dod", 90.0)
    base_year1 = base_result["year_table"].iloc[0]["POI Incl Aux - Discharge (MWh)"]
    scen_year1 = scenario_result["year_table"].iloc[0]["POI Incl Aux - Discharge (MWh)"]
    assert scen_year1 < base_year1


def test_validation_flags_zero_containers():
    from core.validation import validate_container_inputs
    results = validate_container_inputs({
        "dc_capacity_per_container": 2.2, "num_containers": 0,
        "aux_discharge_per_container_mw": 0.006, "aux_charge_per_container_mw": 0.006,
    })
    assert any(lvl == "error" for lvl, _ in results)
