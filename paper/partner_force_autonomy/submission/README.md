# Submission source package

Generated from the canonical manuscript by `prepare_submission.py`.

- Working target: Security Studies
- Canonical manuscript: `../manuscript.md`
- Anonymized review manuscript: `manuscript_anonymized.md`
- Separate author/title page: `title_page.md`
- Canonical manuscript source word count: 12,999
- Main figures: regenerated from tracked evidence before packaging
- Bibliography: closed and validated by `../validate_manuscript.py`

Build sequence:

1. `python ../prepare_submission.py`
2. `python ../render_submission.py`
3. `python ../qa_submission.py`

The anonymized manuscript removes the YAML author and affiliation fields. The
scientific text, citations, tables, disclosure language, and numerical claims
are otherwise unchanged from the canonical manuscript.
