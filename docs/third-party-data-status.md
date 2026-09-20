# Third-party data status

This page summarizes redistribution status recorded in the historical case
source manifests. It is a provenance and publication aid, not legal advice and
not a statement that every source has equal scientific quality.

## Case summary

| Case | Sources | Permitted | Metadata only | Permission required | Review required |
|---|---:|---:|---:|---:|---:|
| Afghanistan 2004-2021 | 5 | 4 | 0 | 0 | 1 |
| Colombia 1984-2016 | 9 | 2 | 0 | 1 | 6 |
| Iraq 2003-2011 | 4 | 2 | 1 | 1 | 0 |
| Nepal 2001-2006 | 6 | 1 | 3 | 2 | 0 |
| Vietnam 1955-1975 | 7 | 5 | 0 | 1 | 1 |

Across these manifests there are currently 14 permitted sources, 4
metadata-only sources, 5 permission-required sources, and 8 review-required
sources.

## Sources not cleared for ordinary redistribution

### Afghanistan

- CSO 2016 population cross-check - **review required**.

### Colombia

- CNMH OMC ArcGIS municipality-year aggregate - **review required**.
- CNMH Portal de Datos / paramilitary structure presence records -
  **review required**.
- CNMH DAV ACPB control points - **review required**.
- CNMH DAV control/presence acquisition index - **review required**.
- CNMH flattened control/presence inventory - **review required**.
- CNMH DAV ACPB/ACMM control points - **review required**.
- GADM administrative boundaries - **permission required** for redistribution
  under the recorded academic/non-commercial terms.

### Iraq

- SIGIR Rusafa case-study material - **metadata only** by default because
  embedded third-party material may carry separate rights.
- GADM administrative boundaries - **permission required** for redistribution.

### Nepal

- OHCHR Nepal Conflict Report - **metadata only** under the recorded UN
  copyright/permission terms.
- Nepal 2001 census material - **permission required** under the recorded NSO
  research-use terms.
- INSEC victim-profile and complete-report sources - **metadata only** by
  default under the recorded non-profit/acknowledgement terms.
- GADM historical district boundaries - **permission required** for
  redistribution.

### Vietnam

- Underlying NARA electronic Vietnam record series - **review required** at
  the item/series level; public-use versions and restrictions can differ by
  series.
- GADM administrative boundaries - **permission required** for redistribution.

## Repository rule

A source being publicly downloadable does not automatically mean Pineland may
republish it. Raw and processed historical inputs remain outside ordinary Git
tracking even when redistribution is permitted. Public case packages should
prefer provenance, hashes, acquisition/transformation scripts, schemas, and
redistributable derivatives.

The enforceable policy is in
[data-redistribution.md](data-redistribution.md). The repository audit fails if
a source artifact with an unresolved or restrictive redistribution state is
tracked at its declared local path.
