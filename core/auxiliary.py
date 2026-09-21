"""
core/auxiliary.py

Section 13 — Auxiliary Energy Module.

Distinguishes:
    Container Auxiliary      = Num Containers x Aux Consumption / Container
    Additional Auxiliary     = 0 unless the user enables + supplies a value
    Standby Energy           = 0 unless the user enables + supplies a value

Total auxiliary energy = Container Aux + Additional Aux + Standby Energy,
with no double counting: Additional Auxiliary and Standby Energy are
independent, mutually-exclusive line items the user opts into explicitly.
"""


def container_auxiliary_load(num_containers: float, aux_per_container_mw: float) -> float:
    return float(num_containers) * float(aux_per_container_mw)


def resolve_additional_auxiliary(aux_cfg: dict) -> float:
    if aux_cfg.get("additional_aux_enabled"):
        return float(aux_cfg.get("additional_aux_value", 0) or 0)
    return 0.0


def resolve_standby_energy(aux_cfg: dict) -> float:
    if aux_cfg.get("standby_enabled"):
        return float(aux_cfg.get("standby_value", 0) or 0)
    return 0.0


def total_extra_aux_energy_mwh(aux_cfg: dict) -> dict:
    """Returns the additional-auxiliary + standby-energy MWh contributions
    that should be ADDED on top of the (Aux Load MW x Time h) container-aux
    term computed elsewhere (in discharge.py / charge.py), per Section 13.
    """
    additional = resolve_additional_auxiliary(aux_cfg)
    standby = resolve_standby_energy(aux_cfg)
    return {
        "additional_aux_mwh": additional,
        "standby_energy_mwh": standby,
        "total_extra_mwh": additional + standby,
    }
