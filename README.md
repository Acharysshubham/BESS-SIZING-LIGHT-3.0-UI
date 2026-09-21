# BESS Sizing & Engineering Analysis Platform

A professional Battery Energy Storage System (BESS) sizing, performance,
augmentation, requirement-matching and what-if analysis tool — built as a
Streamlit application with an independent, pure-Python calculation engine.

> "Do not merely calculate the BESS. Help the engineer understand the BESS."

## What it does

- Year-wise DC and AC performance calculation (discharge & charge)
- FAT/SAT timeline modelling
- Battery degradation (SOH, calendar degradation, DOD)
- Auxiliary consumption, additional auxiliary and standby energy
- Multi-event battery augmentation with AC MV energy roll-up
- POI energy/capacity, DC-DC RTE, AC RTE (excl./incl. auxiliary)
- Requirement matching against tender/contractual values (MATCHED / NOT
  MATCHED, with margin and % margin)
- A deterministic **Engineering Analyzer**: before/after scenario
  recalculation, parameter sensitivity sweeps, side-by-side scenario
  comparison, and a change log — with no fabricated numbers; everything is
  re-derived from the actual calculation engine
- Full calculation traceability (value, unit, formula, inputs) for every
  result
- A professional, auditable multi-sheet Excel export (OpenPyXL), with
  green/red conditional formatting on requirement status
- Save / load project as JSON
- Automated pytest test suite for the core engine

## Project structure

```
bess_sizing/
├── app.py                    # Streamlit application (UI)
├── requirements.txt
├── README.md
├── core/                     # Pure-Python calculation engine (no Streamlit)
│   ├── units.py               # % <-> decimal, safe division, unit-mismatch flags
│   ├── validation.py           # Section 40 input validation rules
│   ├── timeline.py             # FAT/SAT/Year timeline construction
│   ├── base_calculations.py    # Installed DC capacity, DC guarantee capacity
│   ├── discharge.py            # AC efficiency chain, C-rate/time, POI discharge
│   ├── charge.py                # Charging chain, DC-DC RTE, charge POI
│   ├── auxiliary.py             # Container / additional / standby auxiliary
│   ├── augmentation.py          # Augmentation events, augmented DC/AC energy
│   ├── rte.py                    # AC RTE helpers
│   ├── requirements.py           # MATCHED/NOT MATCHED + margin
│   ├── analyzer.py               # What-if, sensitivity, scenario comparison
│   └── engine.py                 # Orchestrator: config -> full year-wise model
├── export/
│   └── excel_export.py           # Multi-sheet auditable OpenPyXL workbook
├── tests/
│   └── test_engine.py            # pytest unit tests for the core engine
└── examples/
    └── sample_project.json       # Example project you can load in the app
```

The calculation engine (`core/`) is completely independent of Streamlit —
every function takes plain dicts/numbers in and returns plain
dicts/DataFrames out, so it can be tested, reused in a CLI, or swapped onto
a different UI later.

## Engineering methodology note

The formulas implemented here follow the methodology supplied in the
project's master specification exactly — they are **not** re-derived,
simplified, or "corrected." Where the source methodology contains a
unit or dimensional ambiguity (for example, combining an MW auxiliary
load with an MWh energy term), the software preserves the supplied
formula and raises a visible **Engineering Unit Check** warning instead
of silently changing it. See the "Engineering Analysis" tab and the
`warnings` list returned by `core.engine.compute_full_model`.

## Running it

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Running the tests

```bash
pytest tests/ -v
```

## Loading the sample project

In the app sidebar, use **Load Project** and select
`examples/sample_project.json`, or paste its contents into the JSON loader.

## Extending it

The architecture is designed so new modules (PCS sizing, cable sizing,
CAPEX/OPEX, dispatch simulation, EMS/SCADA integration, etc. — see
Section 52 of the master spec) can be added as new files under `core/`
and new tabs under `app.py` without touching the existing calculation
chain. An external LLM/API can also be wired into `core/analyzer.py` to
turn its structured before/after diffs into narrative engineering
explanations — the analyzer's deterministic numerical layer will keep
working standalone either way.
