# Historical data redistribution policy

Pineland can be public even when some historical input data cannot be
redistributed. The repository should make that distinction explicit rather
than treating "source is cited" and "source may be republished" as the same
thing.

## Required source-manifest fields

Before public release, every source entry in a case
`data/manifests/sources.json` should record:

- **provider** and dataset/source name;
- **source URL** or stable catalog identifier;
- **version/date**, when the source is versioned;
- **license** or a `license_url` when a formal license exists;
- **redistribution** status;
- **acquisition status**;
- a checksum for any acquired local artifact;
- a citation/provenance note sufficient for another researcher to locate the
  source.

Use one of these redistribution states:

- `permitted` - the source terms permit redistribution under documented
  conditions;
- `metadata_only` - Pineland may publish provenance, scripts, hashes, and
  derived instructions, but not the source artifact;
- `permission_required` - redistribution requires permission not yet recorded;
- `prohibited` - the artifact must not be distributed from the repository;
- `review_required` - terms have not yet been verified.

If attribution or non-commercial conditions apply, record them separately
rather than hiding them inside free-form prose.

## Repository behavior

Raw and processed historical-data directories are ignored by Git by default.
That is useful protection, but it is not a substitute for documenting terms.

For non-redistributable inputs, a public case package should still retain:

- acquisition/build scripts where allowed;
- source identifiers and URLs;
- hashes of the exact local artifacts used;
- transformation code;
- schemas and crosswalks;
- derived products that are themselves redistributable;
- a clear explanation of what the reproducer must obtain independently.

## Current status

The tracked Afghanistan, Colombia, Iraq, Nepal, and Vietnam source manifests now
record an explicit license/rights source and redistribution disposition for
every listed source. A disposition of `review_required` is intentionally not
treated as permission: it means the source may be used internally under the
current research workflow, but the source artifact must not be shipped with a
public release until the missing rights question is resolved.

`scripts/public_release_audit.py` reports missing fields and unresolved
`review_required` entries automatically. The audit does **not** infer legal
rights from provider identity or public accessibility.
