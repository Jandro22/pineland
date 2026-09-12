# Historical Database Portfolio (Standard v2)

> **Fail-Closed Provenance & Zero-Historical-Tuning Contract**
>
> This database layer provides standardized, prospective historical observations across six conflict environments.
> In accordance with the scientific constitution of the Pineland research program:
> 1. **Zero Historical Tuning**: No Pineland structural parameters, synthetic mechanism equations, or latent state coordinates are fit, calibrated, or tuned to historical data.
> 2. **Explicit Observation Semantics**: The standard rigorously distinguishes observed events, observed zeros (within an explicit source frame), source gaps, and sealed holdouts.
> 3. **Non-Violence Measurement Independence**: Latent control and organizational variables require independent non-violence measurement streams rather than circular derivation from violence outcomes.
> 4. **Reproducible Provenance**: All bundles, sources, and builder transformations are strictly fingerprinted with SHA-256.

**Standard SHA-256**: `c94113a221547d2878295cdb2c29350ac64517cea31370cd03fd62800faee0ea`  
**Builder SHA-256**: `5d27ac5013b8ded51353965c5d73bfee49d69662c53f6a6e38ebe7eb0c982857`  
**Registry Timestamp**: `2026-09-12T00:17:49.199640+00:00`  

## Portfolio Summary

| Case ID | Country | License Level | Units | Events | Mapping Rate | Unit-Time Rows | Aux Obs | Bundle Size | Validator |
|---|---|---|---|---|---|---|---|---|---|
| `afghanistan_2004_2021` | Afghanistan | **EXPERIMENT_READY** | 435 | 38796 | 98.31% | 31280 | 808 | 0.68 MiB | **PASS** |
| `nepal_2001_2006` | Nepal | **EXPERIMENT_READY** | 75 | 4743 | 99.96% | 19575 | 95 | 0.12 MiB | **PASS** |
| `colombia_1984_2016` | Colombia | **VERIFICATION_LIMITED** | 1119 | 13906 | 99.48% | 443124 | 23032 | 0.73 MiB | **PASS** |
| `iraq_2003_2011` | Iraq | **VERIFICATION_LIMITED** | 102 | 3348 | 100.00% | 10812 | 106 | 0.10 MiB | **PASS** |
| `vietnam_1955_1975` | Republic of Vietnam (South Vietnam) | **VERIFICATION_LIMITED** | 50 | 595499 | 99.36% | 12200 | 15330 | 11.31 MiB | **PASS** |
| `nigeria_2014` | Nigeria | **SEALED_HOLDOUT** | 37 | 0 | N/A (Sealed) | 37 | 0 | 0.04 MiB | **PASS** |

## Case Details & Governance

### 1. Afghanistan (2004–2021) — `afghanistan_2004_2021`
- **License**: `EXPERIMENT_READY`
- **Role**: Primary longitudinal benchmark for persistent counterinsurgency dynamics.
- **Canonical Units**: 34 harmonized provinces (primary weekly panel) and 401 districts (secondary event mapping); 435 units in geography.
- **Event Frame**: UCDP GED 26.1 (2004–2021), 38,796 retained events (98.31% mapping rate).
- **Auxiliary Streams**: SIGAR quarterly district control assessments (808 auxiliary observations) preserved as raw categorical distributions.

### 2. Nepal (2001–2006) — `nepal_2001_2006`
- **License**: `EXPERIMENT_READY`
- **Role**: Primary civil war benchmark for rapid territorial contestation and state crisis.
- **Canonical Units**: 75 historical districts (weekly panel across 2001–2006, 19,575 panel rows).
- **Event Frame**: UCDP GED 26.1 (2001–2006), 4,743 events (99.96% mapping rate).
- **Auxiliary Streams**: Independent Eastern region adjudicated control/presence records plus INSEC Conflict Victims Report cumulative district totals (95 auxiliary observations total; 74 observed districts, 15,027 cumulative victims).

### 3. Colombia (1984–2016) — `colombia_1984_2016`
- **License**: `VERIFICATION_LIMITED`
- **Role**: Extended multi-actor insurgent conflict with dense municipal geography.
- **Canonical Units**: 1119 GADM Level 2 municipalities (monthly panel across 1984–2016, 443,124 unit-month observations).
- **Event Frame**: UCDP GED 26.1 (1984–2016), 13,906 events with 99.48% mapped to GADM2 polygons.
- **Auxiliary Streams**: CNMH DAV armed structure control/presence inventory (399 records) and CNMH OMC civilian-harm and victim database (22,633 municipality-year records, 384,039 victims; 23,032 auxiliary observations total).
- **Blocked Reasons**: Independent non-violence control/capacity evidence is not yet nationally dense across all 33 years.

### 4. Iraq (2003–2011) — `iraq_2003_2011`
- **License**: `VERIFICATION_LIMITED`
- **Role**: Post-invasion sectarian and insurgent conflict.
- **Canonical Units**: 102 GADM Level 2 districts (monthly panel across 2003–2011, 10,812 unit-month observations).
- **Event Frame**: UCDP GED 26.1 (2003–2011), 3,348 events with 100.00% mapped to GADM2 polygons.
- **Auxiliary Streams**: SIGIR Rusafa urban governance and reconstruction monthly panel (106 auxiliary observations).
- **Blocked Reasons**: Independent control/capacity evidence is an urban anchor slice (Rusafa), not a nationwide surface.

### 5. Vietnam (1955–1975) — `vietnam_1955_1975`
- **License**: `VERIFICATION_LIMITED`
- **Role**: Large-scale historical counterinsurgency benchmark.
- **Canonical Units**: 50 historical HES South Vietnam provinces (monthly panel across 1955–1975, 12,200 unit-month observations).
- **Event Frame**: Cleaned MACV/NARA ground combat archival extract (1963–1975 South Vietnam ground operations), 595,499 events with 99.36% mapped to historical HES provinces.
- **Auxiliary Streams**: HAMLA hamlet-aggregated population control shares (government, VC, neither/both) and HES70 security/control/administration/law-enforcement macromodels (15,330 auxiliary observations total).
- **Blocked Reasons**: Cleaned extract to direct NARA row/layout parity certification pending; NAPE/TFES human-capital operator not yet materialized.

### 6. Nigeria (2014) — `nigeria_2014`
- **License**: `SEALED_HOLDOUT`
- **Role**: External prospective holdout (Boko Haram campaign in northeastern Nigeria, 2014).
- **Holdout Firewall**: The builder does not open or read the raw GED 2014 target archive. The `events.parquet` table contains 0 rows.
- **Canonical Units**: 37 GADM Level 1 administrative units for pre-outcome demographic/geographic exposure only.

## One-Command Verification

To validate the entire historical portfolio fail-closed in one call:
```bash
python -m pytest tests/test_historical_database_v2.py -v
```
Or using the validator script directly:
```bash
python studies/research_program/scripts/validate_historical_database_v2.py \
  studies/afghanistan_2004_2021/data/standard_v2 \
  studies/nepal_2001_2006/data/standard_v2 \
  studies/colombia_1984_2016/data/standard_v2 \
  studies/iraq_2003_2011/data/standard_v2 \
  studies/vietnam_1955_1975/data/standard_v2 \
  studies/research_program/external_validation/nigeria_2014/standard_v2
```
